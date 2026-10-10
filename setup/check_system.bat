@echo off
REM D-Storify POC - system check (changes nothing)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0check_system.ps1"
echo.
pause
