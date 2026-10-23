@echo off
setlocal
cd /d "%~dp0"
LaboratorioMedidas.exe --production
if errorlevel 1 pause
