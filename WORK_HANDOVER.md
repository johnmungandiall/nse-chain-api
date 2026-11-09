# WORK_HANDOVER — nse-chain-api

**Date:** 09-Nov-2026
**Handover from:** kbcode session (automated build)
**Handover to:** any developer / future session continuing this project

---

## 1. What this project is

A **local FastAPI server** that exposes the **NSE (National Stock Exchange, India) option-chain data**
as a clean JSON API for other applications, plus a web **dashboard** and an **API playground**.

Key facts:
- Data is fetched **live from NSE's own JSON API** (`/api/option-chain-v3`) — no browser, no scraping of HTML.
- Every option (CE and PE) in the response carries **IV + delta + gamma + vega**.
  - IV policy: `nse → solved-from-LTP → interpolated → approx-cross-expiry` (flagged per option via `iv_source`).
- Settled (already-expired) expiries are **skipped** and rejected (`HTTP 422`) because Greeks are undefined at TTM=0.
- CORS is enabled, server binds to `0.0.0.0` → usable by other apps on the same machine AND on the LAN.

---

## 2. Folder layout (`Desktop\nse-chain-api\`)

| File | Purpose |
|---|---|
| `nse_fastapi.py` | FastAPI server (API + serves dashboard/playground) |
| `nse_dashboard.html` | Web dashboard UI (option chain table, highlighting, API docs section) |
| `nse_playground.html` | Interactive API testing page |
| `nse_optionchain_headless.py` | Headless fetch CLI (one expiry → raw NSE JSON) |
| `nse_optionchain_to_structured.py` | Pipeline: raw JSON → structured JSON with IV/Greeks |
| `nse_optionchain_full_fetch.py` | Full fetch CLI (all live expiries → full structured JSON) |
| `nifty_optionchain_sample.json` | Raw NSE JSON sample (latest fetch used by transformer) |
| `nifty_optionchain_structured.json` | Structured single-expiry output (latest) |
| `nifty_optionchain_full_structured.json` | Structured full-file output (all live expiries) |
| `nifty_optionchain_best.html` | One-off "best instruments" highlight report (saved earlier) |

Also present: `.git` (repo, branches: `master`, `dev` (current), `1.0.0`), `__pycache__/`.

---

## 3. How to run the server

```powershell
cd $env:USERPROFILE\Desktop\nse-chain-api
python -m uvicorn nse_fastapi:app --host 0.0.0.0 --port 8910
```

- Dashboard: `http://127.0.0.1:8910/`
- Playground: `http://127.0.0.1:8910/playground`
- OpenAPI docs: `http://127.0.0.1:8910/docs`
- LAN access: `http://<this-machine-ip>:8910` (e.g. `http://192.168.1.33:8910`)

Python requirements: `fastapi`, `uvicorn[standard]` (installed in user site-packages; no other deps — HTTP calls are done via `curl.exe` subprocess).

---

## 4. API reference

### `GET /api/option-chain`
| Param | Default | Notes |
|---|---|---|
| `symbol` | `NIFTY` | NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY, NIFTYNXT50, or equity (RELIANCE, HDFCBANK, TCS, SBIN, …) |
| `type` | `Indices` | `Indices` or `Equities` |
| `expiry` | latest live | e.g. `17-Nov-2026`; omit for latest live |

Response:
```json
{
  "meta": { "symbol": "NIFTY", "type": "Indices", "expiry": "17-Nov-2026",
            "underlying_value": 25044.65, "timestamp": "...", "strikes": 131,
            "iv_policy": "nse -> solved-from-LTP -> interpolated" },
  "records": [
    { "strike_price": 25000, "expiry": "17-Nov-2026",
      "dte_days": 7.9931, "ttm_years": 0.021898782343987823,
      "ce": { "ltp": 251.9, "oi": 86869, "chg_oi": 40072, "volume": 655218,
               "bid": 252.1, "ask": 253.55, "bid_qty": 130, "ask_qty": 65,
               "iv": 14.19, "iv_source": "nse", "delta": 0.564844,
               "gamma": 0.00074854, "vega": 14.5897 },
      "pe": { "... same shape ..." } }
  ]
}
```

Errors:
- `422` if the requested expiry has already settled (Greeks undefined).
- `502` if NSE itself fails / is unreachable.

### `GET /api/expiries`
`?symbol=NIFTY` → `{ "symbol": "NIFTY", "expiries": ["17-Nov-2026", …], "skipped_settled": ["09-Nov-2026"] }`

---

## 5. Fetch pipeline (CLI)

```powershell
# single expiry → raw NSE JSON
python nse_optionchain_headless.py --expiry 17-Nov-2026 --save nifty_optionchain_sample.json

# raw → structured (IV + Greeks)
python nse_optionchain_to_structured.py

# all live expiries → full structured JSON
python nse_optionchain_full_fetch.py
```

Outputs land in this folder (paths are project-relative).

---

## 6. Git state

- Repo root: `Desktop\nse-chain-api\` (moved here from Desktop on 09-Nov-2026)
- Branches:
  - `master` — initial commit `f5e374d`
  - `dev` — current working branch (fixes for null IV/Greeks committed as `9087947`)
  - `1.0.0` — created (empty of further changes so far) for release tagging
- Git binary is NOT on PATH on this machine; use full path:
  `C:\Program Files\Git\bin\git.exe`

---

## 7. Known notes / gotchas

- **Settled expiries:** never compute Greeks for TTM=0 (division by ~0). The API rejects them; the full-fetch skips them.
- **Untraded far-dated series:** some have no NSE IV and no traded price; pipeline fills IV with a cross-expiry ATM proxy (marked `iv_source: "approx-cross-expiry"`). Verify before heavy quantitative use.
- **NSE keeps bot protection:** curl with a browser User-Agent, a primed cookie jar, and `Referer: https://www.nseindia.com/option-chain` is required. Do not switch to bare `urllib` for fetching (it gets 403).
- **Data is live + intraday:** NSE timestamps update continuously; no caching beyond a 20 s in-process cache in the API.
- **Windows only assumptions:** `curl.exe`, PowerShell command examples, `C:\` paths.

---

## 8. Suggested next steps (not blocked, not done)

- Publish install/run steps in a README (this file is the handover; a README for contributors is still open).
- Pin dependencies in `requirements.txt` (fastapi, uvicorn).
- Consider a small auth layer / API key if the server will be exposed beyond the LAN.
- Containerize (Dockerfile) if multi-machine deployment is wanted.

---

*End of handover.*
