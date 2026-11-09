#!/usr/bin/env python3
"""Local FastAPI server: NSE option chain data + dashboard + playground.

Endpoints:
  GET /                       dashboard (HTML)
  GET /playground             playground (HTML)
  GET /api/expiries?symbol=NIFTY
  GET /api/option-chain?symbol=NIFTY&type=Indices&expiry=17-Nov-2026

Data is fetched live from NSE's own JSON API (cookie-primed curl), then every
CE/PE is enriched with IV (nse -> solved-from-LTP -> interpolated) and
Black-Scholes delta/gamma/vega — the same pipeline as nse_optionchain_to_structured.py.

Run:  python -m uvicorn nse_fastapi:app --host 127.0.0.1 --port 8000
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

PROJECT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_DIR))

from nse_optionchain_to_structured import (  # noqa: E402
    fill_ivs, bs_greeks, parse_ist,
    EXPIRY_SETTLE_HOUR, EXPIRY_SETTLE_MINUTE,
)

BASE = "https://www.nseindia.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
CURL = "curl.exe"
JAR = os.path.join(tempfile.gettempdir(), "nse_fastapi_cookies.txt")
CACHE_TTL = 20.0

app = FastAPI(title="NSE Option Chain API", version="1.0.0")

# Allow other applications (web apps, scripts, LAN clients) to call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_cache = {}


def _curl(args, timeout=30):
    r = subprocess.run([CURL, "-s", "-A", UA, *args],
                       capture_output=True, timeout=timeout)
    return r.stdout.decode("utf-8", "replace"), r.returncode


def _http_json(url):
    body, rc = _curl(["-b", JAR, "-w", "\n%{http_code}", "-H", "Accept: application/json",
                      "-H", f"Referer: {BASE}/option-chain", url])
    parts = body.rsplit("\n", 1)
    raw = parts[0] if len(parts) == 2 else body
    status = parts[1].strip() if len(parts) == 2 else "?"
    if status != "200":
        raise RuntimeError(f"NSE HTTP {status}: {url}")
    return json.loads(raw)


def _prime():
    _curl(["-c", JAR, BASE + "/"])


def _slim(side):
    if not isinstance(side, dict):
        return None
    return {
        "ltp": side.get("lastPrice"),
        "oi": side.get("openInterest"),
        "chg_oi": side.get("changeinOpenInterest"),
        "volume": side.get("totalTradedVolume"),
        "bid": side.get("bidPrice"),
        "ask": side.get("askPrice"),
        "bid_qty": side.get("bidQuantity"),
        "ask_qty": side.get("askQuantity"),
        "impliedVolatility": side.get("impliedVolatility"),
    }


def _fetch_payload(symbol, typ, expiry):
    key = (symbol, typ, expiry)
    now = time.time()
    hit = _cache.get(key)
    if hit and now - hit[0] < CACHE_TTL:
        return hit[1]

    _prime()
    if not expiry:
        info = _http_json(f"{BASE}/api/option-chain-contract-info?symbol={symbol}")
        dates = info.get("expiryDates") or []
        if not dates:
            raise HTTPException(status_code=502, detail="No expiries returned by NSE")
        now = datetime.now(timezone(timedelta(hours=5, minutes=30)))
        live = [d for d in dates
                if (parse_ist(d) or now).replace(hour=EXPIRY_SETTLE_HOUR,
                                                 minute=EXPIRY_SETTLE_MINUTE,
                                                 second=0, microsecond=0) > now]
        expiry = (live or dates)[0]

    data = _http_json(f"{BASE}/api/option-chain-v3?type={typ}&symbol={symbol}&expiry={expiry}")
    records = data.get("records") or {}
    rows = records.get("data") or []
    S = records.get("underlyingValue")
    now_dt = parse_ist(records.get("timestamp"))

    out_records = []
    for r in rows:
        K = r.get("strikePrice")
        if K is None:
            continue
        exp_dt = parse_ist(r.get("expiryDates")) or parse_ist(r.get("expiryDate"))
        ttm = dte = None
        if exp_dt and now_dt:
            settle = exp_dt.replace(hour=EXPIRY_SETTLE_HOUR, minute=EXPIRY_SETTLE_MINUTE,
                                    second=0, microsecond=0)
            ttm = max((settle - now_dt).total_seconds(), 0.0) / (365.0 * 86400.0)
            dte = round(ttm * 365.0, 4)
        out_records.append({
            "strike_price": K,
            "expiry": expiry,
            "dte_days": dte,
            "ttm_years": ttm,
            "ce": _slim(r.get("CE")),
            "pe": _slim(r.get("PE")),
        })

    def _iv_proxy(side):
        vals = [sd["iv"] for rec in out_records for sd in [rec.get(side)]
                if sd and sd.get("iv") is not None
                and abs(rec["strike_price"] - S) <= 500]
        return (sum(vals) / len(vals)) if vals else None

    fill_ivs(out_records, S,
             fallback={"ce": _iv_proxy("ce"), "pe": _iv_proxy("pe")})

    for rec in out_records:
        for side, is_put in (("ce", False), ("pe", True)):
            sd = rec.get(side)
            if not sd:
                continue
            iv = sd.get("iv")
            sigma = (iv / 100.0) if iv and iv > 0 else None
            g = bs_greeks(S, rec["strike_price"], rec["ttm_years"], sigma,
                           is_put=is_put) if sigma else None
            if g:
                sd["delta"], sd["gamma"], sd["vega"] = g
            else:
                sd["delta"] = sd["gamma"] = sd["vega"] = None

    payload = {
        "meta": {
            "symbol": symbol, "type": typ, "expiry": expiry,
            "underlying_value": S,
            "timestamp": records.get("timestamp"),
            "strikes": len(out_records),
            "iv_policy": "nse -> solved-from-LTP -> interpolated",
        },
        "records": out_records,
    }
    _cache[key] = (now, payload)
    return payload


@app.get("/api/expiries")
def api_expiries(symbol: str = "NIFTY"):
    _prime()
    try:
        info = _http_json(f"{BASE}/api/option-chain-contract-info?symbol={symbol}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    dates = info.get("expiryDates", [])
    now = datetime.now(timezone(timedelta(hours=5, minutes=30)))
    live = [d for d in dates
            if (parse_ist(d) or now).replace(hour=EXPIRY_SETTLE_HOUR,
                                             minute=EXPIRY_SETTLE_MINUTE,
                                             second=0, microsecond=0) > now]
    return {"symbol": symbol,
            "expiries": live,
            "skipped_settled": [d for d in dates if d not in live]}


@app.get("/api/option-chain")
def api_option_chain(symbol: str = "NIFTY", type: str = "Indices",
                     expiry: str | None = None):
    if expiry:
        exp_dt = parse_ist(expiry)
        now = datetime.now(timezone(timedelta(hours=5, minutes=30)))
        if exp_dt and exp_dt.replace(hour=EXPIRY_SETTLE_HOUR,
                                     minute=EXPIRY_SETTLE_MINUTE,
                                     second=0, microsecond=0) <= now:
            raise HTTPException(
                status_code=422,
                detail=f"Expiry {expiry} has already settled (TTM=0) — Greeks are "
                       f"undefined. Use a live expiry, e.g. the one from "
                       f"/api/expiries.")
    try:
        return _fetch_payload(symbol, type, expiry)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"NSE fetch failed: {e}") from e


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return (PROJECT_DIR / "nse_dashboard.html").read_text(encoding="utf-8")


@app.get("/playground", response_class=HTMLResponse)
def playground():
    return (PROJECT_DIR / "nse_playground.html").read_text(encoding="utf-8")
