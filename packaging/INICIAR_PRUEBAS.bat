@echo off
setlocal
cd /d "%~dp0"
LaboratorioMedidas.exe --demo
if errorlevel 1 pause
