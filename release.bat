@echo off
cd /d "%~dp0"

echo === Building Release ===

pip show pyinstaller >nul 2>&1 || pip install pyinstaller

pyinstaller Popup.spec

echo.
echo === Building Installer ===

"%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" installer.iss

echo.
echo === Done ===
echo EXE: dist\Popup.exe
echo Installer: installer\Popup_Setup.exe
pause
