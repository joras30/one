@echo off
setlocal
cd /d "%~dp0"
echo Cierra primero la aplicacion. Esta recuperacion queda en la auditoria.
LaboratorioMedidas.exe --production --reset-admin
pause
