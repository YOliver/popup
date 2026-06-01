[Setup]
AppName=MdViewer
AppVersion=1.2.0
AppPublisher=MdViewer
DefaultDirName={autopf}\MdViewer
DefaultGroupName=MdViewer
OutputDir=installer
OutputBaseFilename=MdViewer_Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile=app_icon.ico
UninstallDisplayIcon={app}\MdViewer.exe

[Files]
Source: "dist\MdViewer.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "app_icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\MdViewer"; Filename: "{app}\MdViewer.exe"; IconFilename: "{app}\app_icon.ico"
Name: "{group}\Uninstall MdViewer"; Filename: "{uninstallexe}"
Name: "{autodesktop}\MdViewer"; Filename: "{app}\MdViewer.exe"; IconFilename: "{app}\app_icon.ico"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加选项:"

[Run]
Filename: "{app}\MdViewer.exe"; Description: "启动 MdViewer"; Flags: nowait postinstall skipifsilent
