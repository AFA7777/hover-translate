@echo off
REM ASCII only -- see make_shortcut.py for why.
cd /d "%~dp0"
python make_shortcut.py
if errorlevel 1 pause
exit /b %errorlevel%
