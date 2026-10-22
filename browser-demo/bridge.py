"""Reuse the application in a browser sandbox with synthetic, individual data."""
import base64
import hashlib
import io
import json
import sqlite3
from email.message import Message
from pathlib import Path
from types import SimpleNamespace

import app
from js import browserPbkdf2

app.pw_hash = lambda password, salt: str(browserPbkdf2(password, salt, app.PASSWORD_ROUNDS))
MAX_DATABASE_BYTES = 23 * 1024 * 1024


class BrowserHandler(app.Handler):
    def send_response(self, code, message=None):
        self.browser_status = code

    def send_header(self, keyword, value):
        self.browser_headers[keyword] = str(value)

    def end_headers(self):
        pass

    def log_message(self, fmt, *args):
        pass


def initialise_demo():
    app.configure('/demo-data', port=8766, demo=True)
    app.init_db()
    app.seed_demo()


def bridge_request(message, cookie):
    request = object.__new__(BrowserHandler)
    request.path = message['path']
    request.command = message.get('method', 'GET').upper()
    request.server = SimpleNamespace(server_port=8766)
    request.client_address = ('127.0.0.1', 1)
    request.headers = Message()
    for name, value in message.get('headers', {}).items():
        if name.lower() not in ('host', 'origin', 'cookie', 'content-length'):
            request.headers[name] = str(value)
    request.headers['Host'] = '127.0.0.1:8766'
    request.headers['Origin'] = 'http://127.0.0.1:8766'
    request.headers['Cookie'] = cookie
    body = str(message.get('body') or '').encode('utf-8')
    request.headers['Content-Length'] = str(len(body))
    request.rfile, request.wfile = io.BytesIO(body), io.BytesIO()
    request.browser_status, request.browser_headers = 200, {}
    request._dispatch(request.command)
    return json.dumps({'status': request.browser_status, 'headers': request.browser_headers,
                       'body_base64': base64.b64encode(request.wfile.getvalue()).decode()})


def snapshot():
    with app.database() as db:
        db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    contents = app.DB_PATH.read_bytes()
    if len(contents) > MAX_DATABASE_BYTES:
        raise ValueError('La demo alcanzó su límite de almacenamiento. Descarga un respaldo y conserva tu prueba actual.')
    return base64.b64encode(contents).decode()


def replace_database(encoded, validate=False):
    contents = base64.b64decode(encoded, validate=True)
    if len(contents) > MAX_DATABASE_BYTES or not contents.startswith(b'SQLite format 3\0'):
        raise ValueError('El respaldo no contiene una base de demostración válida.')
    candidate = Path('/restore-check.db')
    if validate:
        candidate.write_bytes(contents)
        try:
            with sqlite3.connect(str(candidate)) as db:
                if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise ValueError('El respaldo no pasó la comprobación de integridad.')
                if db.execute('PRAGMA user_version').fetchone()[0] > app.SCHEMA_VERSION:
                    raise ValueError('Actualiza la demo antes de restaurar este respaldo.')
                tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if not {'users', 'production_events', 'activity_versions'} <= tables:
                    raise ValueError('El respaldo pertenece a otra aplicación.')
        finally:
            candidate.unlink(missing_ok=True)
    for suffix in ('-wal', '-shm'):
        Path(str(app.DB_PATH) + suffix).unlink(missing_ok=True)
    app.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    incoming = app.DB_PATH.with_suffix('.incoming')
    incoming.write_bytes(contents)
    incoming.replace(app.DB_PATH)


def make_backup():
    encoded = snapshot()
    return json.dumps({'format': 'laboratorio-browser-demo', 'version': 1,
                       'sha256': hashlib.sha256(base64.b64decode(encoded)).hexdigest(),
                       'database_base64': encoded})


def restore_backup(contents):
    backup = json.loads(contents)
    if backup.get('format') != 'laboratorio-browser-demo' or backup.get('version') != 1:
        raise ValueError('Selecciona un respaldo descargado de esta demo gratuita.')
    encoded = backup.get('database_base64', '')
    if len(encoded) > 32 * 1024 * 1024:
        raise ValueError('El respaldo supera el tamaño admitido.')
    digest = hashlib.sha256(base64.b64decode(encoded, validate=True)).hexdigest()
    if digest != backup.get('sha256'):
        raise ValueError('El respaldo está incompleto o dañado.')
    replace_database(encoded, validate=True)
    app.init_db()
    with app.database() as db:
        db.execute('DELETE FROM sessions')

