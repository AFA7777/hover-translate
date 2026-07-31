@echo off
REM ASCII-named alias of the Chinese-named installer. Same behaviour.
REM Keep this file pure ASCII -- even a comment in Chinese breaks cmd parsing,
REM because cmd reads .bat byte-by-byte in the OEM codepage. All Chinese
REM messages are printed by install.py instead.
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
