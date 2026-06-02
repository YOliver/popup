@echo off
cd /d "%~dp0"
pip show PySide6 >nul 2>&1 || pip install -r requirements.txt
python md_viewer.py %*
