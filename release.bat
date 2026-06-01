@echo off
cd /d "%~dp0"

echo === Building Release ===

pip show pyinstaller >nul 2>&1 || pip install pyinstaller

pyinstaller --onefile --windowed --icon=app_icon.ico --name MdViewer md_viewer.py

echo.
echo === Building Installer ===

"%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" installer.iss

echo.
echo === Done ===
echo EXE: dist\MdViewer.exe
echo Installer: installer\MdViewer_Setup.exe
pause
