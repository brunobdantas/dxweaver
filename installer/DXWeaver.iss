#define MyAppName "DXWeaver"
#define MyAppVersion "0.3.3"
#define MyAppPublisher "DXWeaver Project"
#define MyAppExeName "DXWeaver.exe"

[Setup]
AppId={{D2A9507D-DC09-4E3C-AF69-E4DC1D85A7A3}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\installer-output
OutputBaseFilename=DXWeaver-{#MyAppVersion}-Setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupLogging=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked
Name: "autostart"; Description: "Start DXWeaver when I sign in"; GroupDescription: "Startup:"; Flags: unchecked

[Dirs]
Name: "{userappdata}\DXWeaver"

[Files]
Source: "..\dist\DXWeaver.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\config.example.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\config.pu2bru-wrl.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\config.example.json"; DestDir: "{userappdata}\DXWeaver"; DestName: "config.json"; Flags: onlyifdoesntexist

[Icons]
Name: "{group}\DXWeaver"; Filename: "{app}\DXWeaver.exe"; Parameters: "--config ""{userappdata}\DXWeaver\config.json"""; WorkingDir: "{userappdata}\DXWeaver"
Name: "{userdesktop}\DXWeaver"; Filename: "{app}\DXWeaver.exe"; Parameters: "--config ""{userappdata}\DXWeaver\config.json"""; WorkingDir: "{userappdata}\DXWeaver"; Tasks: desktopicon
Name: "{userstartup}\DXWeaver"; Filename: "{app}\DXWeaver.exe"; Parameters: "--config ""{userappdata}\DXWeaver\config.json"" --no-browser"; WorkingDir: "{userappdata}\DXWeaver"; Tasks: autostart

[Run]
Filename: "{app}\DXWeaver.exe"; Parameters: "--config ""{userappdata}\DXWeaver\config.json"""; WorkingDir: "{userappdata}\DXWeaver"; Description: "Launch DXWeaver Operator Console"; Flags: nowait postinstall skipifsilent
