#define MyAppName "AVI Independent Auto Editor"
#define MyAppVersion "0.3.4"
[Setup]
AppId={{9E502F2E-9BE0-4D9B-956C-908889631124}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={localappdata}\Programs\AVI Independent Auto Editor
DefaultGroupName=AVI Independent Auto Editor
OutputBaseFilename=AVI_Auto_Editor_v034_Setup
OutputDir=dist
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
WizardStyle=modern

[Files]
Source: "AVI_Auto_Editor.py"; DestDir: "{app}"
Source: "install_auto.py"; DestDir: "{app}"
Source: "setup_all.py"; DestDir: "{app}"
Source: "setup_bootstrap.ps1"; DestDir: "{app}"
Source: "diagnose.py"; DestDir: "{app}"
Source: "requirements.txt"; DestDir: "{app}"
Source: "requirements-ai.txt"; DestDir: "{app}"
Source: "CAI_MOT_LAN.bat"; DestDir: "{app}"
Source: "CHAY_AUTO_EDIT.bat"; DestDir: "{app}"
Source: "README_VI.md"; DestDir: "{app}"
Source: "footage_tags_EXAMPLE.csv"; DestDir: "{app}"
Source: "autoedit\*.py"; DestDir: "{app}\autoedit"
Source: "tools\*.txt"; DestDir: "{app}\tools"

[Icons]
Name: "{group}\Auto Editor"; Filename: "{app}\CHAY_AUTO_EDIT.bat"; WorkingDir: "{app}"
Name: "{group}\Cai dat Auto Editor"; Filename: "{app}\CAI_MOT_LAN.bat"; WorkingDir: "{app}"
Name: "{userdesktop}\Auto Editor"; Filename: "{app}\CHAY_AUTO_EDIT.bat"; WorkingDir: "{app}"; Tasks: desktopicon

[Tasks]
Name: desktopicon; Description: "Create desktop shortcut"

[Run]
Filename: "{app}\CAI_MOT_LAN.bat"; Description: "Install missing AI dependencies and Qwen (Internet required)"; Flags: postinstall shellexec skipifsilent runasoriginaluser
