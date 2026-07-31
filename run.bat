@echo off
REM ASCII-named alias of the Chinese-named launcher. Same behaviour.
REM Starts the program with a console window so you can see its messages.
REM Keep this file pure ASCII -- see setup.bat for why.
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
