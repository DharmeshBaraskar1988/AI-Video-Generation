@echo off
REM D-Storify POC - installer. Windows may ask for permission while installing Node.js, Python, FFmpeg and Git.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
echo.
pause
