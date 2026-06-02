[Setup]
AppName=Popup
AppVersion=1.3.0
AppPublisher=Popup
DefaultDirName={autopf}\Popup
DefaultGroupName=Popup
OutputDir=installer
OutputBaseFilename=Popup_Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile=app_icon.ico
UninstallDisplayIcon={app}\Popup.exe

[Files]
Source: "dist\Popup.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "app_icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Popup"; Filename: "{app}\Popup.exe"; IconFilename: "{app}\app_icon.ico"
Name: "{group}\Uninstall Popup"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Popup"; Filename: "{app}\Popup.exe"; IconFilename: "{app}\app_icon.ico"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加选项:"

[Run]
Filename: "{app}\Popup.exe"; Description: "启动 Popup"; Flags: nowait postinstall skipifsilent
