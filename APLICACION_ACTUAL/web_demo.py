"""Demo web sintética para una instancia detrás de un proxy HTTPS.

No se utiliza desde los iniciadores locales. El proveedor termina HTTPS y debe
preservar Host/Origin. LAB_DATA_DIR debe apuntar a un volumen persistente propio.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import app


MARKER = '.laboratorio-web-demo.json'
MARKER_CONTENT = {'kind': 'laboratorio-web-demo', 'version': 1}


@dataclass(frozen=True)
class WebSettings:
    origin: str
    data_dir: Path
    port: int
    bind_host: str
    admin_password: str = field(repr=False)


def settings_from_environment(environ=None):
    env = os.environ if environ is None else environ
    origin = app.validate_public_origin(env.get('LAB_PUBLIC_ORIGIN') or env.get('RENDER_EXTERNAL_URL'))
    raw_dir = str(env.get('LAB_DATA_DIR') or '').strip()
    if not raw_dir or not Path(raw_dir).is_absolute():
        raise ValueError('LAB_DATA_DIR debe indicar una carpeta absoluta exclusiva para la demo web.')
    data_dir = Path(raw_dir).resolve()
    for local in (app.ROOT / 'datos_locales', app.ROOT / 'datos_demo'):
        if data_dir == local.resolve() or data_dir.is_relative_to(local.resolve()):
            raise ValueError('La demo web no puede utilizar las carpetas de datos de la aplicación local.')
    if data_dir == data_dir.parent or data_dir == app.ROOT.resolve():
        raise ValueError('LAB_DATA_DIR debe indicar una carpeta exclusiva para la demo web.')
    try:
        port = int(env.get('PORT', '10000'))
    except ValueError:
        raise ValueError('PORT debe ser un puerto válido.') from None
    if not 0 <= port <= 65535:
        raise ValueError('PORT debe ser un puerto válido.')
    bind_host = str(env.get('LAB_BIND_HOST') or '0.0.0.0')
    if bind_host not in ('0.0.0.0', '127.0.0.1'):
        raise ValueError('LAB_BIND_HOST debe ser 0.0.0.0 o 127.0.0.1.')
    password = app.validate_password(env.get('LAB_ADMIN_PASSWORD'), 'supervisor_demo', 'administrador')
    if password == 'LaboratorioDemo2026!':
        raise ValueError('La demo web necesita una contraseña privada distinta de la demo local.')
    return WebSettings(origin, data_dir, port, bind_host, password)


def prepare_data_directory(directory):
    """Solo abrir una carpeta nueva o una demo web previamente marcada."""
    directory = Path(directory)
    marker = directory / MARKER
    if marker.exists():
        if marker.is_symlink():
            raise ValueError('El marcador de demo web no es válido.')
        try:
            content = json.loads(marker.read_text(encoding='utf-8'))
        except (ValueError, OSError):
            raise ValueError('El marcador de demo web no es válido.') from None
        if content != MARKER_CONTENT:
            raise ValueError('El marcador de demo web no es válido.')
        return
    if directory.exists() and any(directory.iterdir()):
        raise ValueError('La carpeta contiene archivos sin marcador de demo web; no se abrirá ni migrará esa base.')
    directory.mkdir(parents=True, exist_ok=True)
    # El marcador se crea antes de inicializar: un reinicio después de una caída
    # puede completar init_db y la semilla transaccional sin importar otra base.
    with marker.open('x', encoding='utf-8') as target:
        json.dump(MARKER_CONTENT, target)
    try:
        directory.chmod(0o700)
        marker.chmod(0o600)
    except OSError:
        pass


def create_server(settings):
    app.configure(settings.data_dir, settings.port, demo=True, public_origin=settings.origin)
    server = app.ThreadingHTTPServer((settings.bind_host, settings.port), app.Handler, bind_and_activate=False)
    try:
        server.server_bind()
        prepare_data_directory(settings.data_dir)
        app.init_db()
        app.seed_demo(admin_password=settings.admin_password)
        server.server_activate()
    except BaseException:
        server.server_close()
        raise
    return server


def main():
    if sys.version_info < (3, 11):
        raise SystemExit('Se necesita Python 3.11 o superior.')
    try:
        settings = settings_from_environment()
        server = create_server(settings)
    except (ValueError, OSError) as error:
        raise SystemExit(str(error)) from None
    print(f'Demo web de evaluación lista. Solo datos ficticios. {settings.origin}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
