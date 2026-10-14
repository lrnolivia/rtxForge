; rtxForge for Windows: setup.
;
; Packages one self-contained `dotnet publish` folder (the WinUI 3 app plus
; the bundled engine and private Python from windows/build/Bundle-Engine.ps1),
; so users install nothing else. Built by windows/build/Build-Installer.ps1
; locally and by .github/workflows/windows-build.yml in CI:
;
;   ISCC /DAppVersion=1.0.0-rc.1 /DArch=x64 /DSourceDir=<publish dir> /O<out> rtxForge.iss
;
; Installs per user by default (no admin prompt, %LOCALAPPDATA%\Programs);
; "Install for all users" is offered in the wizard. Uninstall removes the app
; only: settings, logs and original-file backups in %LOCALAPPDATA%\rtxForge
; stay, so Restore Original Files keeps working after a reinstall.

#ifndef AppVersion
  #define AppVersion "0.0.0-dev"
#endif
#ifndef Arch
  #define Arch "x64"
#endif
#ifndef SourceDir
  #error Pass /DSourceDir=<dotnet publish output with engine and python>
#endif

; Windows file versions are numeric: 1.0.0-rc.1 -> 1.0.0.0.
#define NumericVersion Copy(AppVersion, 1, Pos("-", AppVersion + "-") - 1) + ".0"

[Setup]
AppId={{6E0C2B7A-3F4D-4E8B-9A51-7C2D8F1E4B90}
AppName=rtxForge
AppVersion={#AppVersion}
AppVerName=rtxForge {#AppVersion}
AppPublisher=loew.fi
AppPublisherURL=https://github.com/lrnolivia/rtxForge
AppSupportURL=https://github.com/lrnolivia/rtxForge/issues
AppUpdatesURL=https://github.com/lrnolivia/rtxForge/releases
VersionInfoVersion={#NumericVersion}
VersionInfoProductName=rtxForge
VersionInfoDescription=rtxForge Setup
DefaultDirName={autopf}\rtxForge
DefaultGroupName=rtxForge
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
#if Arch == "arm64"
ArchitecturesAllowed=arm64
ArchitecturesInstallIn64BitMode=arm64
#else
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
#endif
MinVersion=10.0.19041
SetupIconFile=..\RtxForge.Windows\Assets\rtxforge.ico
UninstallDisplayIcon={app}\rtxForge.exe
UninstallDisplayName=rtxForge
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
CloseApplications=yes
RestartApplications=no
OutputBaseFilename=rtxForge-Setup-{#AppVersion}-{#Arch}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "gamemodeicon"; Description: "Add an ""rtxForge Game Mode"" shortcut (full screen, controller friendly)"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; An upgrade replaces the bundled engine and Python wholesale, so files a
; newer engine dropped can never be imported by mistake.
Type: filesandordirs; Name: "{app}\engine"
Type: filesandordirs; Name: "{app}\python"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\rtxForge"; Filename: "{app}\rtxForge.exe"
Name: "{autoprograms}\rtxForge Game Mode"; Filename: "{app}\rtxForge.exe"; Parameters: "--game-mode"; Tasks: gamemodeicon
Name: "{autodesktop}\rtxForge"; Filename: "{app}\rtxForge.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\rtxForge.exe"; Description: "{cm:LaunchProgram,rtxForge}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Byte-code caches the engine may write next to itself (it normally runs with -B).
Type: filesandordirs; Name: "{app}\engine"
Type: filesandordirs; Name: "{app}\python"
