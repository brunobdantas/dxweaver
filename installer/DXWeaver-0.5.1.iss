#define MyAppName "DXWeaver"
#define MyAppVersion "0.5.1"
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
OutputBaseFilename=DXWeaver-0.5.1-Setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
CloseApplications=yes
RestartApplications=no
SetupLogging=yes
LicenseFile=..\dxweaver-package\COPYING-GPL-3.0.txt

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na Área de Trabalho"; GroupDescription: "Atalhos:"; Flags: unchecked

[Files]
Source: "..\dxweaver-package\*"; DestDir: "{app}"; Excludes: "settings\*"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\dxweaver-package\settings\*"; DestDir: "{app}\settings"; Excludes: "resources\dxweaver\DxTheme.qss"; Flags: ignoreversion recursesubdirs createallsubdirs onlyifdoesntexist
Source: "..\dxweaver-package\settings\resources\dxweaver\DxTheme.qss"; DestDir: "{app}\settings\resources\dxweaver"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\DXWeaver"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\DXWeaver"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir DXWeaver"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent
