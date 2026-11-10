# Cheatsheet — the commands and snippets you reach for most.

Copy-paste ready. Group by task; keep each line runnable.

## Run / build / test
- `python -m uvicorn nse_fastapi:app --host 0.0.0.0 --port 8910` — run the API server (dashboard at /, playground at /playground)
- `"C:\Users\John\AppData\Local\Programs\Inno Setup 6\ISCC.exe" setup_install.iss` — build the Windows installer (NSSM service setup)
- `tools\nssm.exe` — bundled NSSM 2.24 (win64) used by install_service.bat / uninstall_service.bat

## Common tasks
- (task) -> `command`

See [[overview]] for first-time setup and [[gotchas]] for what to avoid.
