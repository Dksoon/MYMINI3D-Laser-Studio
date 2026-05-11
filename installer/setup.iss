; =====================================================================
; MYMINI3D Laser Studio — Inno Setup installer script
; Build with:  ISCC.exe installer\setup.iss
; =====================================================================

#define AppName       "MYMINI3D Laser Studio"
#define AppVersion    "2.1.8"
#define AppPublisher  "MYMINI3D"
#define AppExeName    "MYMINI3D Laser Studio.exe"
#define AppId         "{{A3F2C8D1-7B4E-4A9F-B6E2-1D5C8F3A2E91}"
#define DistDir       "..\dist\MYMINI3D Laser Studio"

[Setup]
AppId={#AppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} v{#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL=https://github.com/Dksoon/MYMINI3D-Laser-Studio
AppSupportURL=https://github.com/Dksoon/MYMINI3D-Laser-Studio/issues
AppUpdatesURL=https://github.com/Dksoon/MYMINI3D-Laser-Studio/releases

; Require admin — needed for Program Files install and pnputil driver install
PrivilegesRequired=admin
; Run as 64-bit installer on 64-bit Windows (avoids WOW64 System32 redirection)
ArchitecturesInstallIn64BitMode=x64compatible
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes

; Output
OutputDir=..\release
OutputBaseFilename=MYMINI3D_Laser_Studio_v{#AppVersion}_Setup
SetupIconFile=icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
CompressionThreads=auto

; Windows version requirement
MinVersion=10.0

; Allow silent installs (used by auto-updater)
; Run:  Setup.exe /SILENT /NORESTART
AllowNoIcons=yes

; UI
WizardStyle=modern
ShowLanguageDialog=no

; IMPORTANT: Never delete user data on uninstall
; Data lives in %APPDATA%\MYMINI3D — untouched by installer/uninstaller

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon";   Description: "Create a &desktop shortcut";          GroupDescription: "Additional icons:"
Name: "installdriver"; Description: "Install K40 USB driver automatically"; GroupDescription: "Hardware setup:"; \
  Flags: checkedonce

[Files]
; Copy entire PyInstaller output folder
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Bundle K40 driver files alongside the app
Source: "..\drivers\k40_winusb.inf";         DestDir: "{app}\drivers"; Flags: ignoreversion
Source: "..\drivers\K40_Laser.inf";          DestDir: "{app}\drivers"; Flags: ignoreversion; Check: FileExists(ExpandConstant('{src}\..\drivers\K40_Laser.inf'))
Source: "..\drivers\K40_Driver_Install.exe"; DestDir: "{app}";         Flags: ignoreversion; Check: FileExists(ExpandConstant('{src}\..\drivers\K40_Driver_Install.exe'))
Source: "..\drivers\libusb0.dll";            DestDir: "{app}";         Flags: ignoreversion; Check: FileExists(ExpandConstant('{src}\..\drivers\libusb0.dll'))

; ── Factory data bundle (only present if build.ps1 found data) ──────
; Only installed on FRESH INSTALL — existing user data is NEVER overwritten.
; The Check function below detects whether a database already exists.
#ifdef BundleData
Source: "..\installer\bundled_data\*"; \
  DestDir: "{userappdata}\MYMINI3D"; \
  Flags: ignoreversion recursesubdirs createallsubdirs; \
  Check: ShouldInstallBundledData
#endif

[Icons]
; Start menu
Name: "{group}\{#AppName}";       Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
; Desktop (optional task)
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
; Install K40 USB driver if task was ticked (full path — {sys} = C:\Windows\System32)
Filename: "{sysnative}\pnputil.exe"; \
  Parameters: "/add-driver ""{app}\drivers\k40_winusb.inf"" /install"; \
  StatusMsg: "Installing K40 USB driver..."; \
  Flags: runhidden; Tasks: installdriver

; Launch app after install (user can untick)
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; \
  Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Only delete app files — NEVER touch %APPDATA%\MYMINI3D
Type: filesandordirs; Name: "{app}"

[Registry]
; Register app for Add/Remove Programs with uninstall info
Root: HKLM; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#AppId}"; \
  ValueType: string; ValueName: "DisplayName"; ValueData: "{#AppName}"
Root: HKLM; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#AppId}"; \
  ValueType: string; ValueName: "DisplayVersion"; ValueData: "{#AppVersion}"
Root: HKLM; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#AppId}"; \
  ValueType: string; ValueName: "Publisher"; ValueData: "{#AppPublisher}"

[Code]
// ─────────────────────────────────────────────────────────────────────
// Only install bundled factory data on a FRESH install.
// If a database already exists the user has live data — leave it alone.
// ─────────────────────────────────────────────────────────────────────

function ShouldInstallBundledData(): Boolean;
var
  DBPath: String;
begin
  DBPath := ExpandConstant('{userappdata}\MYMINI3D\mymini3d.db');
  // Return TRUE only when no database exists yet (fresh install)
  Result := not FileExists(DBPath);
end;

// ─────────────────────────────────────────────────────────────────────
// Close the running app before updating (silent update support)
// ─────────────────────────────────────────────────────────────────────

function FindAndCloseApp(): Boolean;
var
  ResultCode: Integer;
begin
  // Attempt to close gracefully via taskkill
  Exec('taskkill.exe', '/F /IM "MYMINI3D Laser Studio.exe"',
       '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := True;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
  begin
    FindAndCloseApp();
    Sleep(800);   // give it a moment to close
  end;
end;

// ─────────────────────────────────────────────────────────────────────
// Show "update successful" message only on silent upgrades
// ─────────────────────────────────────────────────────────────────────
procedure DeinitializeSetup();
begin
  // Nothing needed — app launches itself via [Run] section
end;
