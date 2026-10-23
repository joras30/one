"""Construcción Windows sin incluir datos ni credenciales de ninguna instalación."""
from pathlib import Path
import hashlib
import shutil
import subprocess
import sys
from zipfile import ZipFile,ZIP_DEFLATED

ROOT=Path(__file__).resolve().parents[1]
if sys.platform!='win32':raise SystemExit('Esta construcción se ejecuta en Windows.')
subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onedir','--console',
    '--name','LaboratorioMedidas','--add-data','APLICACION_ACTUAL/static;static',
    '--add-data','APLICACION_ACTUAL/assets;assets','--add-data','APLICACION_ACTUAL/catalogos.json;.',
    'APLICACION_ACTUAL/app.py'],cwd=ROOT,check=True)
folder=ROOT/'dist/LABORATORIO_V33_FASE1_WINDOWS'
shutil.copytree(ROOT/'dist/LaboratorioMedidas',folder,dirs_exist_ok=True)
for name in ['INICIAR_PRODUCCION.bat','INICIAR_RED.bat','INICIAR_PRUEBAS.bat','RECUPERAR_ADMIN.bat','LEEME_FASE1.txt']:
    shutil.copy2(ROOT/'packaging'/name,folder/name)
license_file=Path(sys.base_prefix)/'LICENSE.txt'
if license_file.exists():shutil.copy2(license_file,folder/'LICENCIA_PYTHON.txt')
subprocess.run([sys.executable,str(ROOT/'packaging/smoke_windows.py'),str(folder/'LaboratorioMedidas.exe')],check=True)
archive=ROOT/'dist/LABORATORIO_V33_FASE1_WINDOWS.zip'
with ZipFile(archive,'w',ZIP_DEFLATED) as package:
    for path in folder.rglob('*'):
        if path.is_file():
            assert not set(path.parts)&{'datos_produccion','datos_demo','REFERENCIAS','DOCUMENTACION'}
            assert path.suffix.lower() not in {'.db','.sqlite','.sqlite3','.log'}
            package.write(path,Path(folder.name)/path.relative_to(folder))
with ZipFile(archive) as package:assert package.testzip() is None
digest=hashlib.sha256(archive.read_bytes()).hexdigest()
archive.with_suffix('.sha256.txt').write_text(digest+'  '+archive.name+'\n')
print('Paquete Windows verificado; sin bases ni claves precargadas. SHA-256: '+digest)
