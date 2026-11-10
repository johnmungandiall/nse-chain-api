# Changelog — notable changes, newest first.

The ONLY place release history lives (don't duplicate it in other notes).
One line per change that future-you or the agent should know about.

## Unreleased
- Added Inno Setup installer (setup_install.iss → output\NSE_OptionChain_API_Setup_1.0.0.exe) that installs the API as an NSSM Windows service `NSEOptionChainAPI` (auto-start; venv + fastapi/uvicorn created at install; uninstall stops/removes the service). Rebuild: `"C:\Users\John\AppData\Local\Programs\Inno Setup 6\ISCC.exe" setup_install.iss`.
- Playground request builder made comprehensive: expiry dropdown auto-loads live expiries from `/api/expiries`, reset button, endpoint switch dims expiry field (nse_playground.html).
- Fixed `nse_fastapi.py#_fetch_payload` cache-stamp bug: `now` was float at first call but became a `datetime` when expiry was auto-picked; storing it in the cache made the next same-key request crash with `TypeError: unsupported operand type(s) for -: 'float' and 'datetime.datetime'` (HTTP 502). Cache now always stamps `time.time()`, and the IST datetime uses a separate `ist_now` variable.
- Server port changed 8000 → 8910 (unique, avoids clashes) — dashboard docs + handover updated.

## (date) - first version
- Initial knowledge base scaffolded.
