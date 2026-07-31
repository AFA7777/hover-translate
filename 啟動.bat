@echo off
REM ASCII only -- see install.py / make_shortcut.py for why.
REM The program prints its own Chinese startup banner.
cd /d "%~dp0"
title hover_translate
if not exist dict.db goto nodict
python hover_translate.py
if errorlevel 1 pause
exit /b %errorlevel%

:nodict
echo.
echo   Dictionary dict.db not found. Building it now...
echo.
python build_dict.py
if errorlevel 1 pause
exit /b %errorlevel%
