@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
if errorlevel 1 goto folder_error
for %%F in ("app.py" "production.py" "documents.py" "catalogos.json" "static\index.html" "static\app.js" "static\app.css" "assets\edesur.png") do if not exist "%%~F" goto incomplete_package
py -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
if errorlevel 1 goto python_error
py "%~dp0app.py" --demo
if errorlevel 1 goto startup_error
exit /b 0

:incomplete_package
echo.
echo Falta parte de la aplicacion en esta carpeta.
echo Extrae TODO el ZIP antes de abrir probar_demo.bat.
echo En WinRAR: selecciona Extraer en... y elige una carpeta local.
echo Abre la carpeta extraida, luego APLICACION_ACTUAL y probar_demo.bat.
echo En esa carpeta deben estar juntos app.py, production.py y documents.py.
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
pause
exit /b 1
