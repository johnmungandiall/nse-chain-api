@echo off
setlocal
REM NSE Option Chain API - service uninstaller (NSSM)
REM Called by the Inno Setup uninstaller.

set "APP_DIR=%~dp0"
set "NSSM=%APP_DIR%tools\nssm.exe"
set "SERVICE=NSEOptionChainAPI"

if not exist "%NSSM%" (
  echo [ERROR] nssm.exe not found. Skipping service removal.
  exit /b 1
)

echo [*] Stopping service "%SERVICE%"...
"%NSSM%" stop "%SERVICE%" >nul 2>&1

echo [*] Removing service "%SERVICE%"...
"%NSSM%" remove "%SERVICE%" confirm >nul 2>&1

exit /b 0
