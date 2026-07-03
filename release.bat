@echo off
cd /d "%~dp0"

echo === Building Release ===

pip show pyinstaller >nul 2>&1 || pip install pyinstaller

pyinstaller Popup.spec

echo.
echo === Building Installer ===

for /f "tokens=2 delims==" %%a in ('findstr /b "VERSION" version.py') do set VER=%%a
set VER=%VER: =%
set VER=%VER:"=%

"%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" /dMyVersion=%VER% installer.iss

echo.
echo === Done ===
echo EXE: dist\Popup.exe
echo Installer: dist\Popup_Setup_v%VER%.exe
pause
