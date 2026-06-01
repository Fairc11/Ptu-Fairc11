; Ptu v1.4.1 - Inno Setup Installer
#define MyAppName "Ptu"
#define MyAppVersion "1.4.1"
#define MyAppPublisher "Ptu"
#define MyAppExeName "Ptu.exe"

[Setup]
AppId={{B8A3C8E0-4F1A-4A5A-9B2C-1A2B3C4D5E6F}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=installer
OutputBaseFilename=Ptu_Setup_v{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
SetupIconFile=icon.ico
UninstallDisplayName=Ptu v{#MyAppVersion}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"
Name: "startmenuicon"; Description: "Create a Start Menu shortcut"; GroupDescription: "Shortcuts:"

[Files]
; --onedir 模式：复制整个 dist\Ptu\ 目录（含 _internal\）
Source: "dist\Ptu\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: startmenuicon
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动 Ptu"; Flags: postinstall nowait skipifsilent shellexec

[UninstallRun]
Filename: "taskkill"; Parameters: "/f /im Ptu.exe"; Flags: runhidden; RunOnceId: "KillPtu"

[Code]
function IsWebView2Installed: Boolean;
var
  key: string;
begin
  key := 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
  Result :=
    RegKeyExists(HKEY_LOCAL_MACHINE, key) or
    RegKeyExists(HKEY_CURRENT_USER, key) or
    RegKeyExists(HKLM32, key) or
    RegKeyExists(HKCU32, key) or
    DirExists(ExpandConstant('{pf32}\Microsoft\EdgeWebView\Application'));
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if (CurStep = ssPostInstall) and not IsWebView2Installed then
  begin
    if MsgBox('需要 Microsoft Edge WebView2 Runtime 才能运行。是否现在下载安装？',
              mbConfirmation, MB_YESNO) = IDYES then
    begin
      ShellExec('open',
        'https://go.microsoft.com/fwlink/p/?LinkId=2124703',
        '', '', SW_SHOW, ewNoWait, ResultCode);
    end;
  end;
end;
