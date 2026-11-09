#!/usr/bin/env python3
"""Convert raw NSE option-chain JSON to structured JSON with IV for EVERY option.

Every CE/PE gets an IV in one fetch:
  - NSE's reported impliedVolatility when present (iv_source="nse")
  - solved from the traded last price via Black-Scholes bisection when NSE reports 0
    but a price exists (iv_source="solved")
  - linearly interpolated along the same-side strike surface when untraded
    (iv_source="interpolated"); out-of-range strikes use the nearest level
Greeks (delta/gamma/vega) are computed from the filled IV.

Input : Desktop\nifty_optionchain_sample.json (raw /api/option-chain-v3 response)
Output: Desktop\nifty_optionchain_structured.json
"""
import json
import math
import os
import sys
from datetime import datetime, timezone, timedelta

HOME = os.path.expanduser("~")
RAW = os.path.join(HOME, "Desktop", "nifty_optionchain_sample.json")
OUT = os.path.join(HOME, "Desktop", "nifty_optionchain_structured.json")

RISK_FREE = 0.065   # 6.5% p.a.
DIV_YIELD = 0.0
EXPIRY_SETTLE_HOUR = 15
EXPIRY_SETTLE_MINUTE = 30
IV_FLOOR = 0.01     # 1% minimum vol
IV_CEIL = 5.0       # 500% maximum vol


def parse_ist(value):
    txt = str(value).strip()
    for fmt in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y", "%d-%m-%Y", "%d-%m-%Y %H:%M:%S"):
        try:
            dt = datetime.strptime(txt, fmt)
            return dt.replace(tzinfo=timezone(timedelta(hours=5, minutes=30)))
        except ValueError:
            continue
    return None


def norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def norm_pdf(x):
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def bs_price(S, K, T, sigma, r=RISK_FREE, q=DIV_YIELD, is_put=False):
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
        return None
    sqrt_t = math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / (sigma * sqrt_t)
    d2 = d1 - sigma * sqrt_t
    df_q = math.exp(-q * T)
    df_r = math.exp(-r * T)
    if is_put:
        return K * df_r * norm_cdf(-d2) - S * df_q * norm_cdf(-d1)
    return S * df_q * norm_cdf(d1) - K * df_r * norm_cdf(d2)


def implied_vol(S, K, T, price, is_put=False):
    """Bisection: find sigma such that BS price == market price."""
    if S <= 0 or K <= 0 or T <= 0 or price <= 0:
        return None
    lo, hi = IV_FLOOR, IV_CEIL
    if bs_price(S, K, T, lo, is_put=is_put) > price:
        return None  # price below intrinsic floor for min vol
    if bs_price(S, K, T, hi, is_put=is_put) < price:
        return None  # price above max-vol price
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        p = bs_price(S, K, T, mid, is_put=is_put)
        if p < price:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-10:
            break
    return 0.5 * (lo + hi)


def bs_greeks(S, K, T, sigma, r=RISK_FREE, q=DIV_YIELD, is_put=False):
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
        return None
    sqrt_t = math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / (sigma * sqrt_t)
    d2 = d1 - sigma * sqrt_t
    df_q = math.exp(-q * T)
    if is_put:
        delta = df_q * (norm_cdf(d1) - 1.0)
    else:
        delta = df_q * norm_cdf(d1)
    gamma = df_q * norm_pdf(d1) / (S * sigma * sqrt_t)
    vega = S * df_q * norm_pdf(d1) * sqrt_t / 100.0
    return round(delta, 6), round(gamma, 8), round(vega, 4)


def interpolate_iv(iv_points, K):
    """Linear interpolation over (strike, iv) pairs; clamp outside range."""
    pts = [p for p in iv_points if p[1] is not None]
    if not pts:
        return None
    pts.sort()
    ks = [p[0] for p in pts]
    vs = [p[1] for p in pts]
    if K <= ks[0]:
        return vs[0]
    if K >= ks[-1]:
        return vs[-1]
    for i in range(len(ks) - 1):
        if ks[i] <= K <= ks[i + 1]:
            if ks[i + 1] == ks[i]:
                return vs[i]
            f = (K - ks[i]) / (ks[i + 1] - ks[i])
            return vs[i] + f * (vs[i + 1] - vs[i])
    return vs[-1]


def fill_ivs(records, S, fallback=None):
    """First pass per side: nse -> solved; second pass: interpolate leftovers;
    final fallback: cross-expiry ATM proxy when a side has no anchors at all."""
    fallback = fallback or {}
    for side in ("ce", "pe"):
        ordered = [r for r in records if r.get(side)]
        # pass 1: nse / solved
        for r in ordered:
            side_d = r[side]
            iv_raw = side_d.get("impliedVolatility")
            if iv_raw and iv_raw > 0:
                side_d["iv"] = round(float(iv_raw), 4)
                side_d["iv_source"] = "nse"
                continue
            ltp = side_d.get("lastPrice") or 0
            sig = implied_vol(S, r["strike_price"], r["ttm_years"], ltp,
                              is_put=(side == "pe"))
            if sig is not None:
                side_d["iv"] = round(sig, 4)
                side_d["iv_source"] = "solved"
            else:
                side_d["iv"] = None
                side_d["iv_source"] = None
        # pass 2: interpolation for leftovers
        known = [(r["strike_price"], r[side]["iv"]) for r in ordered
                 if r[side].get("iv") is not None]
        for r in ordered:
            if r[side].get("iv") is not None:
                continue
            iv = interpolate_iv(known, r["strike_price"])
            if iv is not None:
                r[side]["iv"] = round(iv, 4)
                r[side]["iv_source"] = "interpolated"
            elif fallback.get(side) is not None:
                r[side]["iv"] = round(float(fallback[side]), 4)
                r[side]["iv_source"] = "approx-cross-expiry"
            else:
                r[side]["iv"] = None
                r[side]["iv_source"] = "unavailable"


def main():
    if not os.path.exists(RAW):
        print(f"[!] input missing: {RAW}", file=sys.stderr)
        sys.exit(1)

    with open(RAW, encoding="utf-8") as f:
        payload = json.load(f)

    records = payload.get("records") or {}
    rows = records.get("data") or []
    S = records.get("underlyingValue")
    now = parse_ist(records.get("timestamp")) or datetime.now(
        timezone(timedelta(hours=5, minutes=30)))

    structured = {
        "meta": {
            "source": "https://www.nseindia.com/api/option-chain-v3",
            "symbol": records.get("underlying") or "NIFTY",
            "underlying_value": S,
            "timestamp": records.get("timestamp"),
            "greek_model": "Black-Scholes (r=6.5%, q=0)",
            "iv_policy": "nse -> solved-from-LTP -> interpolated",
            "total_strikes": len(rows),
        },
        "records": [],
    }

    for r in rows:
        K = r.get("strikePrice")
        if K is None:
            continue
        expiry = parse_ist(r.get("expiryDates")) or parse_ist(r.get("expiryDate"))
        ttm = None
        dte = None
        if expiry:
            settle = expiry.replace(hour=EXPIRY_SETTLE_HOUR, minute=EXPIRY_SETTLE_MINUTE,
                                    second=0, microsecond=0)
            ttm = max((settle - now).total_seconds(), 0.0) / (365.0 * 86400.0)
            dte = round(ttm * 365.0, 4)
        structured["records"].append({
            "strike_price": K,
            "expiry": expiry.strftime("%d-%b-%Y") if expiry else None,
            "dte_days": dte,
            "ttm_years": ttm,
            "ce": json.loads(json.dumps(r.get("CE"))) if r.get("CE") else None,
            "pe": json.loads(json.dumps(r.get("PE"))) if r.get("PE") else None,
        })

    fill_ivs(structured["records"], S)

    # attach greeks from the filled IV
    for rec in structured["records"]:
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

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(structured, f, indent=2, ensure_ascii=False)

    # verification counts
    n_ce = n_pe = 0
    iv_ce = iv_pe = 0
    src_counts = {}
    for rec in structured["records"]:
        for side in ("ce", "pe"):
            sd = rec.get(side)
            if not sd:
                continue
            if side == "ce":
                n_ce += 1
                if sd.get("iv") is not None:
                    iv_ce += 1
            else:
                n_pe += 1
                if sd.get("iv") is not None:
                    iv_pe += 1
            s = sd.get("iv_source")
            src_counts[s] = src_counts.get(s, 0) + 1

    print(f"[i] wrote {OUT}")
    print(f"[i] CE with IV: {iv_ce}/{n_ce} | PE with IV: {iv_pe}/{n_pe}")
    print(f"[i] iv_source distribution: {json.dumps(src_counts)}")
    print(f"[i] meta: {json.dumps(structured['meta'], ensure_ascii=False)}")


if __name__ == "__main__":
    main()
