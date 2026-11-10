# Gotchas — traps specific to this repo. Read before editing.

- Never reuse one variable for both a wall-clock epoch (float) and an IST `datetime` in `nse_fastapi.py#_fetch_payload`. The old code stored `now` in `_cache` after it had been reassigned to a `datetime`, and the next same-key request did `now - hit[0]` (float − datetime) → `TypeError` → HTTP 502. Cache stamp with `time.time()`; keep the IST clock as a separate `ist_now`.
- The playground page (`nse_playground.html`) is served fresh from disk on every GET — no server restart needed for HTML/JS edits.
- Server serves on port 8910 (0.0.0.0); dashboard at `/`, playground at `/playground`, OpenAPI at `/docs`.
- NSE bot protection: curl needs browser User-Agent + primed cookie jar + `Referer: https://www.nseindia.com/option-chain`; bare `urllib` gets 403. Handled inside the server, not the playground.
