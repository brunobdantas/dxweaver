#define MyAppName "MSHV-DXWeaver"
#define MyAppVersion "0.4.0"
#define MyAppPublisher "DXWeaver / PU2BRU"
#define MyAppExeName "MSHV-DXWeaver.exe"

[Setup]
AppId={{F56E6F2D-8074-4C31-98CE-82C7509A4E5A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\installer-output-mshv
OutputBaseFilename=MSHV-DXWeaver-0.4.0-Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
SetupLogging=yes
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na Área de Trabalho"; GroupDescription: "Atalhos:"; Flags: unchecked

[Files]
; Runtime and application files. Existing user settings are deliberately preserved.
Source: "..\mshv-package\*"; DestDir: "{app}"; Excludes: "settings\*"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\mshv-package\settings\*"; DestDir: "{app}\settings"; Flags: ignoreversion recursesubdirs createallsubdirs onlyifdoesntexist

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir {#MyAppName}"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent
