@echo off
REM ASCII only. Chinese text is printed by install.py -- cmd.exe reads .bat
REM files byte-by-byte in the OEM codepage, so non-ASCII content breaks parsing.
cd /d "%~dp0"
python --version >nul 2>&1
if errorlevel 1 goto nopython
python install.py
exit /b %errorlevel%

:nopython
echo.
echo   Python not found.
echo.
echo   Please install Python first:
echo       https://www.python.org/downloads/
echo.
echo   IMPORTANT: tick "Add Python to PATH" at the bottom
echo   of the installer, otherwise it stays undetectable.
echo.
echo   Then run this file again.
echo.
pause
exit /b 1
