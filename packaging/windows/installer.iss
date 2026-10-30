; Inno Setup 6 script for ClassManageSystem (Windows installer).
;
; Build:
;   iscc packaging\windows\installer.iss /DMyAppVersion=3.0.0
;
; Expects PyInstaller output at dist\ClassManageSystem\ (onedir build).
;
; Design notes:
;   * per-user install (PrivilegesRequired=lowest): no admin rights needed,
;     which matters on school machines. Installs under %LOCALAPPDATA%\Programs.
;   * Qt DLLs stay as separate files inside the install directory, so users can
;     replace them (LGPL v3 section 4(d)).
;   * the LICENSE page is shown before installation (Apache-2.0 requires
;     shipping the license text; NOTICE and THIRD-PARTY-NOTICES are installed
;     next to the app).

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif

; 用脚本自身的位置推导仓库根目录，避免依赖 ISCC 的当前工作目录
#define RepoRoot SourcePath + "\..\..\"

#define MyAppName "ClassManageSystem"
#define MyAppDisplayName "Class Management Terminal"
#define MyAppPublisher "Gentole Lee"
#define MyAppExeName "ClassManageSystem.exe"
#define MyAppId "{{8F2A5C1E-7B34-4D9A-9E61-2C7B4F0A6D15}"

[Setup]
AppId={#MyAppId}
AppName={#MyAppDisplayName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppDisplayName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppDisplayName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir={#RepoRoot}dist
OutputBaseFilename=ClassManageSystem-{#MyAppVersion}-Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
SetupIconFile={#SourcePath}\app.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
LicenseFile={#RepoRoot}LICENSE
; The app itself writes data next to the executable; installing under
; %LOCALAPPDATA% keeps that directory writable for the current user.
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
Source: "{#RepoRoot}dist\ClassManageSystem\*"; DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#RepoRoot}LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#RepoRoot}NOTICE"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#RepoRoot}THIRD-PARTY-NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppDisplayName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppDisplayName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppDisplayName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; \
    Description: "{cm:LaunchProgram,{#MyAppDisplayName}}"; \
    Flags: nowait postinstall skipifsilent
