; Ptu v1.4.2 - Inno Setup Installer
#define MyAppName "Ptu"
#define MyAppVersion "1.4.2"
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
Name: "chinesesimp"; MessagesFile: "compiler:Default.isl"

[LangOptions]
LanguageName=简体中文
LanguageID=$0804
LanguageCodePage=65001
DialogFontName=Microsoft YaHei UI
WelcomeFontName=Microsoft YaHei UI

[Messages]
SetupAppTitle=安装
SetupWindowTitle=安装 - %1
UninstallAppTitle=卸载
UninstallAppFullTitle=%1 卸载
InformationTitle=提示
ConfirmTitle=确认
ErrorTitle=错误
SetupLdrStartupMessage=即将安装 %1。是否继续？
AdminPrivilegesRequired=安装本程序需要管理员权限。
SetupAppRunningError=检测到 %1 正在运行。%n%n请先关闭所有 Ptu 窗口，然后点击“确定”继续，或点击“取消”退出安装。
UninstallAppRunningError=检测到 %1 正在运行。%n%n请先关闭所有 Ptu 窗口，然后点击“确定”继续，或点击“取消”退出卸载。
ExitSetupTitle=退出安装
ExitSetupMessage=安装尚未完成。如果现在退出，程序不会被安装。%n%n确定要退出安装吗？
ButtonBack=< 上一步(&B)
ButtonNext=下一步(&N) >
ButtonInstall=安装(&I)
ButtonOK=确定
ButtonCancel=取消
ButtonYes=是(&Y)
ButtonNo=否(&N)
ButtonFinish=完成(&F)
ButtonBrowse=浏览(&B)...
ButtonWizardBrowse=浏览(&B)...
ButtonNewFolder=新建文件夹(&M)
SelectLanguageTitle=选择安装语言
SelectLanguageLabel=请选择安装过程中使用的语言。
ClickNext=点击“下一步”继续，或点击“取消”退出安装。
BrowseDialogTitle=选择文件夹
BrowseDialogLabel=请在列表中选择一个文件夹，然后点击“确定”。
NewFolderName=新建文件夹
WelcomeLabel1=欢迎使用 [name] 安装向导
WelcomeLabel2=本向导将在你的电脑上安装 [name/ver]。%n%n建议继续前关闭其他应用程序。
WizardSelectDir=选择安装位置
SelectDirDesc=要将 [name] 安装到哪里？
SelectDirLabel3=安装程序将把 [name] 安装到以下文件夹。
SelectDirBrowseLabel=点击“下一步”继续。如需选择其他文件夹，请点击“浏览”。
DirExists=文件夹：%n%n%1%n%n已经存在。是否继续安装到该文件夹？
WizardSelectTasks=选择附加任务
SelectTasksDesc=安装时还要执行哪些附加任务？
SelectTasksLabel2=请选择安装 [name] 时要执行的附加任务，然后点击“下一步”。
WizardReady=准备安装
ReadyLabel1=安装程序已准备好开始安装 [name]。
ReadyLabel2a=点击“安装”继续；如需查看或修改设置，请点击“上一步”。
ReadyLabel2b=点击“安装”继续。
ReadyMemoDir=安装位置：
ReadyMemoGroup=开始菜单文件夹：
ReadyMemoTasks=附加任务：
WizardInstalling=正在安装
InstallingLabel=请稍候，正在安装 [name]。
FinishedHeadingLabel=正在完成 [name] 安装向导
FinishedLabelNoIcons=[name] 已成功安装到你的电脑。
FinishedLabel=[name] 已成功安装到你的电脑。你可以通过已创建的快捷方式启动程序。
FinishedRestartLabel=为了完成 [name] 安装，需要重启电脑。是否现在重启？
FinishedRestartMessage=为了完成 [name] 安装，需要重启电脑。%n%n是否现在重启？
StatusSavingUninstall=正在保存卸载信息...
UninstallNotFound=文件 "%1" 不存在，无法卸载。
UninstallOpenError=无法打开文件 "%1"，无法卸载。
ConfirmUninstall=确定要完全移除 %1 及其组件吗？
OnlyAdminCanUninstall=只有拥有管理员权限的用户才能卸载此程序。
UninstallStatusLabel=请稍候，正在从你的电脑中移除 %1。
UninstalledAll=%1 已成功从你的电脑中移除。
UninstalledMost=%1 卸载完成。%n%n部分内容未能自动删除，可以手动删除。
WizardUninstalling=卸载状态
StatusUninstalling=正在卸载 %1...
[CustomMessages]
CreateDesktopIcon=创建桌面快捷方式
CreateStartMenuIcon=创建开始菜单快捷方式

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "快捷方式："
Name: "startmenuicon"; Description: "{cm:CreateStartMenuIcon}"; GroupDescription: "快捷方式："

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
var
  CleanupUserData: Boolean;

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

function InitializeUninstall(): Boolean;
begin
  Result := True;
  CleanupUserData := False;
  if MsgBox(
    '是否同时删除 Ptu 的用户数据和浏览器依赖缓存？' #13#13
    '选择“是”：删除日志、Cookie、下载记录、输出文件，以及 Ptu 下载/内置使用的 Playwright 浏览器缓存。适合彻底重装。' #13#13
    '选择“否”：只卸载程序文件，保留日志、下载内容和登录数据。',
    mbConfirmation, MB_YESNO) = IDYES then
  begin
    CleanupUserData := True;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usPostUninstall) and CleanupUserData then
  begin
    DelTree(ExpandConstant('{localappdata}\Ptu'), True, True, True);
    DelTree(ExpandConstant('{localappdata}\ms-playwright'), True, True, True);
  end;
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
