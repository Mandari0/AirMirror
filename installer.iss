; Inno Setup script for AirMirror - AirPlay receiver for Windows (UxPlay + tray front-end)
#define AppName "AirMirror"
#define AppVersion "1.0.0"
#define AppPublisher "AirMirror"
#define AppExe "AirMirror.exe"

[Setup]
AppId={{97381F0F-4ECC-4345-937C-23BBF7F0DA35}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\AirMirror
DefaultGroupName=AirMirror
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile=airmirror.ico
OutputDir=installer
OutputBaseFilename=AirMirror-Setup-{#AppVersion}
CloseApplications=yes
RestartApplications=no
AllowNoIcons=yes
SetupLogging=yes
AppMutex=Local\AirMirrorAppMutex

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[CustomMessages]
english.AutostartTask=Start with Windows
russian.AutostartTask=Запускать при входе в Windows
english.AutostartGroup=Autostart:
russian.AutostartGroup=Автозапуск:
english.SettingsShortcut=Settings
russian.SettingsShortcut=Настройки
english.DesktopShortcut=AirMirror (iPhone to PC)
russian.DesktopShortcut=AirMirror (iPhone to PC)
english.UninstallShortcut=Uninstall {#AppName}
russian.UninstallShortcut=Удалить {#AppName}
english.FirewallStatus=Configuring Windows Firewall...
russian.FirewallStatus=Настройка брандмауэра...
english.LaunchApp=Launch {#AppName}
russian.LaunchApp=Запустить {#AppName}

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "autostart"; Description: "{cm:AutostartTask}"; GroupDescription: "{cm:AutostartGroup}"

[Files]
Source: "dist\AirMirror\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\AirMirror\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "build\portable\uxplay\*"; DestDir: "{app}\uxplay"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\{cm:SettingsShortcut}"; Filename: "{app}\{#AppExe}"; Parameters: "--settings"
Name: "{group}\{cm:UninstallShortcut}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{cm:DesktopShortcut}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "AirMirror"; ValueData: """{app}\{#AppExe}"""; Tasks: autostart; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "AirMirror"; Flags: dontcreatekey uninsdeletevalue

[Run]
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""AirMirror (UxPlay)"""; Flags: runhidden; StatusMsg: "{cm:FirewallStatus}"
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""AirMirror (UxPlay)"" dir=in action=allow program=""{app}\uxplay\bin\uxplay.exe"" enable=yes profile=private,domain"; Flags: runhidden; StatusMsg: "{cm:FirewallStatus}"
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchApp}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM {#AppExe}"; Flags: runhidden; RunOnceId: "KillTray"
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM uxplay.exe"; Flags: runhidden; RunOnceId: "KillUxPlay"
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""AirMirror (UxPlay)"""; Flags: runhidden; RunOnceId: "DeleteFirewallRule"

[UninstallDelete]
Type: filesandordirs; Name: "{app}\_internal"
Type: filesandordirs; Name: "{app}\uxplay"

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  { stop a running instance so files are not locked }
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM uxplay.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM {#AppExe}', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  { legacy build name, in case it is still running during migration }
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM AirPlayTray.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := '';
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    if not WizardIsTaskSelected('autostart') then
      RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'AirMirror');
  end;
end;
