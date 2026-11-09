#!/usr/bin/env python3
"""Full headless fetch of the NSE option chain: every LIVE expiry, all options.

Skips expiries that have already settled (TTM <= 0) so every remaining contract
has real time-to-expiry and therefore computable Greeks.

IV policy per option: nse -> solved-from-LTP -> interpolated -> cross-expiry
ATM proxy (marked iv_source="approx-cross-expiry") for untraded far-dated series.

Output: Desktop\nifty_optionchain_full_structured.json
"""
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone, timedelta

HOME = os.path.expanduser("~")
SYS_DIR = os.path.join(HOME, "Desktop")
sys.path.insert(0, SYS_DIR)

from nse_optionchain_to_structured import (  # noqa: E402
    fill_ivs, bs_greeks, parse_ist,
    EXPIRY_SETTLE_HOUR, EXPIRY_SETTLE_MINUTE,
)

BASE = "https://www.nseindia.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
CURL = "curl.exe"
JAR = os.path.join(tempfile.gettempdir(), "nse_fullfetch_cookies.txt")
OUT = os.path.join(HOME, "Desktop", "nifty_optionchain_full_structured.json")


def curl(args, timeout=60):
    r = subprocess.run([CURL, "-s", "-A", UA, *args],
                       capture_output=True, timeout=timeout)
    return r.stdout.decode("utf-8", "replace"), r.returncode


def fetch_json(url):
    body, rc = curl(["-b", JAR, "-w", "\n%{http_code}", "-H", "Accept: application/json",
                      "-H", f"Referer: {BASE}/option-chain", url])
    parts = body.rsplit("\n", 1)
    raw = parts[0] if len(parts) == 2 else body
    status = parts[1].strip() if len(parts) == 2 else "?"
    if status != "200":
        raise RuntimeError(f"HTTP {status} for {url}")
    return json.loads(raw)


def is_settled(expiry, now):
    dt = parse_ist(expiry)
    if dt is None:
        return True
    settle = dt.replace(hour=EXPIRY_SETTLE_HOUR, minute=EXPIRY_SETTLE_MINUTE,
                        second=0, microsecond=0)
    return settle <= now


def atm_proxy(records, S, side):
    vals = [sd["iv"] for r in records for sd in [r.get(side)]
            if sd and sd.get("iv") is not None
            and abs(r["strike_price"] - S) <= 500]
    if not vals:
        vals = [sd["iv"] for r in records for sd in [r.get(side)]
                if sd and sd.get("iv") is not None]
    return (sum(vals) / len(vals)) if vals else None


def main():
    # prime cookies
    curl(["-c", JAR, BASE + "/"])

    # every available expiry for NIFTY
    info = fetch_json(f"{BASE}/api/option-chain-contract-info?symbol=NIFTY")
    expiries = info.get("expiryDates") or []
    if not expiries:
        print("[!] no expiryDates returned", file=sys.stderr)
        sys.exit(1)

    now = datetime.now(timezone(timedelta(hours=5, minutes=30)))
    live = [e for e in expiries if not is_settled(e, now)]
    if not live:
        print("[!] no live expiries", file=sys.stderr)
        sys.exit(1)
    print(f"[i] total expiries {len(expiries)}; live {len(live)} (skipping settled)")

    full = {"meta": {"symbol": "NIFTY", "source": BASE + "/api/option-chain-v3",
                     "expiry_count_all": len(expiries),
                     "expiries_all": expiries,
                     "expiry_count_live": len(live),
                     "expiries_live": live},
            "expiries": []}

    reference_fallback = None
    for expiry in live:
        payload = fetch_json(
            f"{BASE}/api/option-chain-v3?type=Indices&symbol=NIFTY&expiry={expiry}")
        records = payload.get("records") or {}
        rows = records.get("data") or []
        S = records.get("underlyingValue")
        now_dt = parse_ist(records.get("timestamp")) or now

        expiry_records = []
        for r in rows:
            K = r.get("strikePrice")
            if K is None:
                continue
            exp_dt = parse_ist(r.get("expiryDates")) or parse_ist(r.get("expiryDate"))
            ttm = dte = None
            if exp_dt:
                settle = exp_dt.replace(hour=EXPIRY_SETTLE_HOUR,
                                        minute=EXPIRY_SETTLE_MINUTE,
                                        second=0, microsecond=0)
                ttm = max((settle - now_dt).total_seconds(), 0.0) / (365.0 * 86400.0)
                dte = round(ttm * 365.0, 4)
            expiry_records.append({
                "strike_price": K,
                "expiry": expiry,
                "dte_days": dte,
                "ttm_years": ttm,
                "ce": json.loads(json.dumps(r.get("CE"))) if r.get("CE") else None,
                "pe": json.loads(json.dumps(r.get("PE"))) if r.get("PE") else None,
            })

        if reference_fallback is None:
            fill_ivs(expiry_records, S)
            reference_fallback = {"ce": atm_proxy(expiry_records, S, "ce"),
                                  "pe": atm_proxy(expiry_records, S, "pe")}
        else:
            fill_ivs(expiry_records, S, fallback=reference_fallback)

        for rec in expiry_records:
            K = rec["strike_price"]
            T = rec["ttm_years"]
            for side, is_put in (("ce", False), ("pe", True)):
                sd = rec.get(side)
                if not sd:
                    continue
                iv = sd.get("iv")
                sigma = (iv / 100.0) if iv and iv > 0 else None
                g = bs_greeks(S, K, T, sigma, is_put=is_put) if sigma else None
                if g:
                    sd["delta"], sd["gamma"], sd["vega"] = g
                else:
                    sd["delta"] = sd["gamma"] = sd["vega"] = None

        full["expiries"].append({
            "expiry": expiry,
            "underlying_value": S,
            "timestamp": records.get("timestamp"),
            "strikes": len(expiry_records),
            "records": expiry_records,
        })
        print(f"[i] {expiry}: {len(expiry_records)} strikes fetched")

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(full, f, indent=2, ensure_ascii=False)

    # verification: per-expiry IV and Greeks coverage
    print(f"[i] wrote {OUT}")
    tot_ce = tot_pe = iv_ce = iv_pe = g_ce = g_pe = 0
    for ex in full["expiries"]:
        nce = npe = ive = ivp = ge = gp = 0
        for rec in ex["records"]:
            if rec.get("ce"):
                nce += 1
                ive += 1 if rec["ce"].get("iv") is not None else 0
                ge += 1 if rec["ce"].get("gamma") is not None else 0
            if rec.get("pe"):
                npe += 1
                ivp += 1 if rec["pe"].get("iv") is not None else 0
                gp += 1 if rec["pe"].get("gamma") is not None else 0
        tot_ce += nce; tot_pe += npe
        iv_ce += ive; iv_pe += ivp; g_ce += ge; g_pe += gp
        print(f"[i] {ex['expiry']}: CE {ive}/{nce} IV {ge}/{nce} G | "
              f"PE {ivp}/{npe} IV {gp}/{npe} G")
    print(f"[i] TOTAL: CE {iv_ce}/{tot_ce} IV {g_ce}/{tot_ce} G | "
          f"PE {iv_pe}/{tot_pe} IV {g_pe}/{tot_pe} G")


if __name__ == "__main__":
    main()
