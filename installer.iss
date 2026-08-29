; Inno Setup 脚本 —— DAP Flash Tool 安装程序
; 说明：用户可自选安装位置；默认按用户目录安装（无需管理员权限）。
; 用 ISCC.exe 编译本脚本，产物输出到 installer\DAPFlashTool-Setup-*.exe

#define MyAppName "DAP Flash Tool"
#define MyAppVersion "0.3.2"
#define MyAppExeName "DAPFlashTool.exe"
; PyInstaller onedir 产物目录名（dist\DAPFlashTool\ -> 安装到 {app}\DAPFlashTool\）
#define MyAppFolder "DAPFlashTool"

[Setup]
AppId={{9A3C5B7D-1E2F-4A5B-8C6D-7E8F9A0B1C2D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=DAPFlashTool
DefaultDirName={autopf}\DAPFlashTool
DefaultGroupName={#MyAppName}
; 允许用户选择任意安装位置（含非管理员可写目录）
PrivilegesRequired=lowest
AllowNoIcons=yes
; 不启用 Inno 6 自带的关闭进程机制（其"自动关闭"会卡死），
; 改为在 [Code] 中用 taskkill 强制结束正在运行的 DAPFlashTool，避免文件被占用。
CloseApplications=no
OutputDir=installer
OutputBaseFilename=DAPFlashTool-Setup-{#MyAppVersion}
SetupIconFile=assets\logo.ico
UninstallDisplayIcon={app}\{#MyAppFolder}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; 简体中文界面
LanguageDetectionMethod=uilanguage
ShowLanguageDialog=yes

[Languages]
Name: "chinesesimplified"; MessagesFile: "langs\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\{#MyAppFolder}\*"; DestDir: "{app}\{#MyAppFolder}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppFolder}\{#MyAppExeName}"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppFolder}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppFolder}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Result := '';
  // 安装文件前，强制结束正在运行的 DAPFlashTool，避免文件被占用（DeleteFile 拒绝访问）。
  // /F 强制终止，/T 结束其子进程；进程不存在时 taskkill 返回非 0 但无害，继续安装。
  Exec('taskkill.exe', '/F /IM DAPFlashTool.exe /T', '', SW_HIDE,
       ewWaitUntilTerminated, ResultCode);
end;
