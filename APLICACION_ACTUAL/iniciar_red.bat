@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
if errorlevel 1 goto folder_error
for %%F in ("app.py" "production.py" "operational.py" "documents.py" "analytics.py" "catalogos.json" "static\index.html" "static\app.js" "static\app.css" "assets\edesur.png") do if not exist "%%~F" goto incomplete_package
py -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
if errorlevel 1 goto python_error
echo.
echo LABORATORIO DE MEDIDAS - RED DE OFICINA
echo La base permanece en el disco local de esta PC principal.
echo Usa la IP privada asignada a esta PC, visible con ipconfig.
echo Ejemplo: 192.168.1.20 - no copies el ejemplo si tu IP es otra.
echo El programa no cambia la IP ni el firewall.
echo.
set "LAB_LAN_IP="
set /p "LAB_LAN_IP=IP privada de esta PC: "
py -c "import os,runpy,sys; sys.argv=['app.py','--lan-ip',os.environ.get('LAB_LAN_IP','')]; runpy.run_path('app.py',run_name='__main__')"
if errorlevel 1 goto startup_error
exit /b 0

:incomplete_package
echo.
echo Falta parte de la aplicacion en esta carpeta.
echo Extrae TODO el ZIP antes de abrir iniciar_red.bat.
echo En WinRAR: selecciona Extraer en... y elige una carpeta local.
echo Abre la carpeta extraida, luego APLICACION_ACTUAL e iniciar_red.bat.
pause
exit /b 1

:python_error
echo.
echo No se pudo ejecutar Python 3.11 o superior con el comando py.
echo Comprueba la instalacion con: py --version
pause
exit /b 1

:folder_error
echo.
echo No se pudo abrir la carpeta de la aplicacion.
echo Extrae TODO el ZIP en una carpeta local e intentalo desde alli.
pause
exit /b 1

:startup_error
echo.
echo La aplicacion no pudo iniciarse. Revisa el mensaje anterior.
echo La IP debe estar asignada a esta PC y la base en su disco local.
pause
exit /b 1
