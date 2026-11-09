#!/usr/bin/env python3
"""
NSE option-chain headless fetcher (no browser needed).

Uses the same JSON endpoints the NSE website itself calls — via curl, because
NSE's bot protection rejects Python's urllib (HTTP 403) while curl passes:
  1. prime session cookies by visiting the homepage (curl -c jar)
  2. GET /api/option-chain-v3?type=...&symbol=...&expiry=... (curl -b jar)

Examples:
  python nse_optionchain_headless.py                          # NIFTY, latest expiry
  python nse_optionchain_headless.py --symbol BANKNIFTY
  python nse_optionchain_headless.py --type Equities --symbol RELIANCE
  python nse_optionchain_headless.py --expiry 17-Nov-2026 --save nifty.json
"""
import argparse
import json
import subprocess
import sys
import tempfile
import os

BASE = "https://www.nseindia.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
CURL = "curl.exe" if os.name == "nt" else "curl"


def curl(args, timeout=60):
    r = subprocess.run([CURL, "-s", "-A", UA, *args],
                       capture_output=True, timeout=timeout)
    return r.stdout.decode("utf-8", "replace"), r.returncode


def main():
    ap = argparse.ArgumentParser(description="Fetch NSE option chain headlessly (curl-backed).")
    ap.add_argument("--symbol", default="NIFTY")
    ap.add_argument("--type", default="Indices", choices=["Indices", "Equities"])
    ap.add_argument("--expiry", default=None, help="e.g. 17-Nov-2026; default = first available")
    ap.add_argument("--save", default=None, help="write the raw JSON to this file")
    args = ap.parse_args()

    jar = os.path.join(tempfile.gettempdir(), "nse_headless_cookies.txt")

    # 1) prime cookies from the homepage
    curl(["-c", jar, BASE + "/"])

    # 2) resolve expiry if not given
    expiry = args.expiry
    if not expiry:
        body, rc = curl(["-b", jar, "-H", "Accept: application/json",
                          "-H", f"Referer: {BASE}/option-chain",
                          f"{BASE}/api/option-chain-contract-info?symbol={args.symbol}"])
        if rc == 0:
            try:
                dates = json.loads(body).get("expiryDates") or []
                if dates:
                    expiry = dates[0]
            except Exception:
                pass
        if not expiry:
            print("[!] could not determine expiry automatically; pass --expiry", file=sys.stderr)
            sys.exit(2)

    # 3) fetch the option chain
    url = f"{BASE}/api/option-chain-v3?type={args.type}&symbol={args.symbol}&expiry={expiry}"
    body, rc = curl(["-b", jar, "-w", "\n%{http_code}", "-H", "Accept: application/json",
                      "-H", f"Referer: {BASE}/option-chain", url])
    parts = body.rsplit("\n", 1)
    raw = parts[0] if len(parts) == 2 else body
    status = parts[1].strip() if len(parts) == 2 else "?"
    print(f"[i] HTTP {status} | type={args.type} symbol={args.symbol} expiry={expiry}")
    if status != "200":
        print(raw[:400], file=sys.stderr)
        sys.exit(1)

    data = json.loads(raw)
    records = data.get("records") or {}
    rows = records.get("data") or []
    print(f"[i] rows (strikes) returned: {len(rows)}")
    if "underlyingValue" in records:
        print(f"[i] underlying spot: {records['underlyingValue']}")
    if rows:
        r0 = rows[len(rows) // 2]
        print("[i] sample mid-row keys present:",
              ", ".join(k for k in ("strikePrice", "CE", "PE", "expiryDate") if k in r0))

    if args.save:
        with open(args.save, "w", encoding="utf-8") as f:
            f.write(raw)
        print(f"[i] saved -> {args.save}")


if __name__ == "__main__":
    main()
