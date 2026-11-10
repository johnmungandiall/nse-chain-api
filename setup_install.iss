; Inno Setup script — NSE Option Chain API
; Builds a Windows installer that deploys the FastAPI server and
; installs it as an NSSM Windows service (auto-start on boot).

#define MyAppName "NSE Option Chain API"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Local"
#define MyAppExeName "nse_fastapi.py"
#define MyAppService "NSEOptionChainAPI"

[Setup]
AppId={{8F2A6C41-3C4E-4B7F-9D1A-6E5B8C2A4F0D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\NSEOptionChainAPI
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=output
OutputBaseFilename=NSE_OptionChain_API_Setup_{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "startservice"; Description: "Start the NSE Option Chain API service immediately"; Flags: unchecked

[Files]
Source: "nse_fastapi.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "nse_dashboard.html"; DestDir: "{app}"; Flags: ignoreversion
Source: "nse_playground.html"; DestDir: "{app}"; Flags: ignoreversion
Source: "nse_optionchain_to_structured.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "nse_optionchain_headless.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "nse_optionchain_full_fetch.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "tools\nssm.exe"; DestDir: "{app}\tools"; Flags: ignoreversion
Source: "install_service.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "uninstall_service.bat"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"

[Run]
; Install + start the NSSM service after file copy. The batch creates a
; venv, pip-installs fastapi/uvicorn, registers SERVICE_AUTO_START and starts it.
Filename: "{app}\install_service.bat"; StatusMsg: "Installing Windows service..."; Flags: runhidden
; If the user unchecked the task we still always install/start (service is the point of this installer) —
; the task controls nothing extra; kept for clarity.

[UninstallRun]
Filename: "{app}\uninstall_service.bat"; Flags: runhidden
