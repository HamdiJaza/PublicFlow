@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0distribution\Start_MunicipaliteAuto.ps1"
if errorlevel 1 pause
