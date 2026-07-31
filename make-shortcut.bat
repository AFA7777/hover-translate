@echo off
REM ASCII-named alias of the Chinese-named shortcut builder. Same behaviour.
REM Keep this file pure ASCII -- even a comment in Chinese breaks cmd parsing,
REM because cmd reads .bat byte-by-byte in the OEM codepage (cp950 here).
cd /d "%~dp0"
python make_shortcut.py
if errorlevel 1 pause
exit /b %errorlevel%
