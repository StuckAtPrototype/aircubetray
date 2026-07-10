; AirCube Tray Inno Setup Script
; Creates a Windows installer for the AirCube system-tray app.
;
; LICENSE and README live one level up (AirCube/), so those paths use ..\.
; Build the .exe first via build_tray.py (or build_installer.py which does both).

#define MyAppName "AirCube Tray"
#define MyAppShortName "AirCubeTray"
#define MyAppVersion "2.0.0"
#define MyAppPublisher "StuckAtPrototype"
#define MyAppURL "https://github.com/stuckatprototype/aircubetray"
#define MyAppExeName "AirCubeTray.exe"

[Setup]
AppId={{A3D4E5F6-7890-4B2C-9D1E-3F5A7B9C1D2E}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppShortName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
LicenseFile=LICENSE
OutputDir=installer_output
OutputBaseFilename=AirCubeTray_Setup_v{#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
; Let the user opt into a per-user install (no UAC prompt, installs into
; %LocalAppData%). Matters because we write to HKCU\Run and {userstartup};
; under a per-user install those correctly map to the actual user's profile.
PrivilegesRequiredOverridesAllowed=dialog
; Intentional: the tray app is per-user (HKCU\Run + {userstartup} shortcut).
; When installing for all users, those entries apply to the installing user's
; profile only, which matches how this app is expected to be used.
UsedUserAreasWarning=no
SetupIconFile=aircube_tray.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} Setup
VersionInfoProductName={#MyAppName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "startup"; Description: "Launch {#MyAppName} at Windows startup"; GroupDescription: "Startup Options:"

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: startup

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Stop the tray app (graceful then force) before files are removed.
Filename: "taskkill"; Parameters: "/IM {#MyAppExeName}"; Flags: runhidden; RunOnceId: "StopAirCubeTray"
Filename: "taskkill"; Parameters: "/F /IM {#MyAppExeName}"; Flags: runhidden; RunOnceId: "KillAirCubeTray"

[UninstallDelete]
; Clean up any empty install folder left behind.
Type: dirifempty; Name: "{app}"

[Registry]
; The app's Settings dialog can register itself in HKCU Run under the name
; "AirCubeTray". Remove that key on uninstall so we don't leave a dangling
; entry pointing at a deleted .exe.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "AirCubeTray"; Flags: deletevalue uninsdeletevalue

[Code]
function AppIsRunning(): Boolean;
var
  ResultCode: Integer;
begin
  // `find` exits 0 only when the image name appears in the tasklist output.
  Result := Exec('cmd.exe',
    '/c tasklist /FI "IMAGENAME eq {#MyAppExeName}" /NH | find /I "{#MyAppExeName}" > nul',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode) and (ResultCode = 0);
end;

procedure CloseRunningApp();
var
  ResultCode: Integer;
begin
  Exec('taskkill', '/IM {#MyAppExeName}', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(500);
  Exec('taskkill', '/F /IM {#MyAppExeName}', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(1000);
end;

function InitializeSetup(): Boolean;
begin
  Result := True;
  if AppIsRunning() then
  begin
    if WizardSilent() or
       (MsgBox('{#MyAppName} is running. Close it now and continue with the installation?',
               mbConfirmation, MB_YESNO) = IDYES) then
      CloseRunningApp()
    else
      Result := False;
  end;
end;

function InitializeUninstall(): Boolean;
var
  ResultCode: Integer;
begin
  Result := True;
  // Try graceful close, then force kill so the .exe is no longer locked.
  Exec('taskkill', '/IM {#MyAppExeName}', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(500);
  Exec('taskkill', '/F /IM {#MyAppExeName}', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(1000);
end;
