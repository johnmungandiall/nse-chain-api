@echo off
setlocal EnableDelayedExpansion
REM NSE Option Chain API - service installer (NSSM)
REM Called by the Inno Setup installer after files are copied.

set "APP_DIR=%~dp0"
set "NSSM=%APP_DIR%tools\nssm.exe"
set "SERVICE=NSEOptionChainAPI"

if not exist "%NSSM%" (
  echo [ERROR] nssm.exe not found in tools\.
  exit /b 1
)

REM ---- locate Python ----
set "PYTHON="
where python >nul 2>&1
if %errorlevel%==0 (
  set "PYTHON=python"
) else (
  where py >nul 2>&1
  if !errorlevel!==0 (
    for /f "delims=" %%i in ('py -3 -c "import sys;print(sys.executable)" 2^>nul') do set "PYTHON=%%i"
  )
)
if not defined PYTHON (
  echo [ERROR] Python 3 not found on PATH (python or py). Install Python 3 first.
  exit /b 1
)

REM ---- create venv once ----
if not exist "%APP_DIR%.venv\Scripts\python.exe" (
  echo [*] Creating virtual environment...
  "%PYTHON%" -m venv "%APP_DIR%.venv"
  if errorlevel 1 (
    echo [ERROR] venv creation failed.
    exit /b 1
  )
  echo [*] Installing Python dependencies (fastapi, uvicorn)...
  "%APP_DIR%.venv\Scripts\python.exe" -m pip install --disable-pip-version-check --quiet fastapi "uvicorn[standard]"
  if errorlevel 1 (
    echo [WARN] pip install reported a non-zero exit; continuing anyway.
  )
)

REM ---- register service ----
echo [*] Installing service "%SERVICE%"...
"%NSSM%" install "%SERVICE%" "%APP_DIR%.venv\Scripts\python.exe" -m uvicorn nse_fastapi:app --host 0.0.0.0 --port 8910
if errorlevel 1 (
  echo [ERROR] nssm install failed (already exists? try uninstall first).
  exit /b 1
)
"%NSSM%" set "%SERVICE%" AppDirectory "%APP_DIR%"
"%NSSM%" set "%SERVICE%" Description "NSE Option Chain API server (FastAPI + uvicorn) on port 8910"
"%NSSM%" set "%SERVICE%" Start SERVICE_AUTO_START
"%NSSM%" set "%SERVICE%" ObjectName LocalSystem
"%NSSM%" set "%SERVICE%" AppStdout "%APP_DIR%logs\service.out.log"
"%NSSM%" set "%SERVICE%" AppStderr "%APP_DIR%logs\service.err.log"

echo [*] Starting service "%SERVICE%"...
"%NSSM%" start "%SERVICE%"
if errorlevel 1 (
  echo [WARN] Service start returned non-zero. Check logs\service.err.log (often port 8910 in use).
)

echo [OK] Service "%SERVICE%" installed. Dashboard: http://127.0.0.1:8910/
exit /b 0
