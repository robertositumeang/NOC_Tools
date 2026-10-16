; Script generated for Inno Setup Compiler
; NOC Tools Installer Script

#define MyAppName "NOC Tools"
#define MyAppVersion "1.0.1"
#define MyAppPublisher "PT. KEREAKTIF Indonesia"
#define MyAppExeName "NOC Tools.exe"

[Setup]
AppId={{5E28B025-A227-4CFB-9524-7EB87B41DE84}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=installer_output
OutputBaseFilename=NOC_Tools_Setup_v1.0.1
SetupIconFile=app_icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; Main Executables
Source: "dist\NOC Tools.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "app_icon.ico"; DestDir: "{app}"; Flags: ignoreversion

; One WebView executable serves both Dashboard and Ticket Checker.
Source: "dist\bin\NOC Web Tools.exe"; DestDir: "{app}\bin"; Flags: ignoreversion

; Standalone PyQt/Playwright application launched from the main app.
Source: "dist\bin\Capture_Modem.exe"; DestDir: "{app}\bin"; Flags: ignoreversion

; External data folder (Site Management, etc.)
Source: "dist\data\*"; DestDir: "{app}\data"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\app_icon.ico"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\app_icon.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
