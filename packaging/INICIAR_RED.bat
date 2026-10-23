@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
set /p "LAB_IP=IP privada de esta PC principal (ejemplo 192.168.1.20): "
LaboratorioMedidas.exe --production --lan-ip "%LAB_IP%"
if errorlevel 1 pause
