"""Laboratorio de Medidas — Control de Producción.

Servidor local del prototipo, ampliado con actividades versionadas. Conserva
las tablas, identificadores y verificadores de contraseña de la versión 0.1.
Ejecución: python app.py; prueba independiente: python app.py --demo.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import errno
import hashlib
import hmac
import json
import math
import os
import re
import secrets
import sqlite3
import sys
import threading
import time
import traceback
import webbrowser
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import documents
import production

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / 'datos_locales'
DB_PATH = DATA_DIR / 'laboratorio.db'
HOST, PORT = '127.0.0.1', 8765
DEFAULT_NORMAL_PORT, DEFAULT_DEMO_PORT = 8765, 8766
DEMO_MODE = False
PUBLIC_ORIGIN = ''
PASSWORD_ROUNDS = 260000
MAX_JSON_BYTES = 12 * 1024 * 1024
LOGIN_FAILS = {}
LOGIN_LOCK = threading.Lock()
LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_MAX_FAILURES = 6
MANAGERS = {'supervisor', 'administrador'}
ROLES = {'tecnico', 'supervisor', 'administrador', 'visitante'}
VERSION = '1.0-pruebas'
SCHEMA_VERSION = 3


def validate_public_origin(value):
    """Un origen HTTPS exacto; nunca aceptar rutas o cabeceras reenviadas."""
    value = str(value or '').strip()
    parsed = urlparse(value)
    try:
        port = parsed.port
    except ValueError:
        raise ValueError('El origen público debe ser una dirección HTTPS sin ruta.') from None
    hostname = parsed.hostname or ''
    dns_name = r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*'
    if (parsed.scheme != 'https' or not re.fullmatch(dns_name, hostname)
            or parsed.username is not None or parsed.password is not None
            or parsed.path not in ('', '/') or parsed.query or parsed.fragment
            or any(char.isspace() for char in value)
            or any(char in value for char in ('\\', '?', '#', '@', '%'))
            or port is not None and not 1 <= port <= 65535):
        raise ValueError('El origen público debe ser una dirección HTTPS sin ruta.')
    return 'https://' + hostname + (f':{port}' if port not in (None, 443) else '')


def configure(data_dir=None, port=8765, demo=False, *, public_origin=None):
    global DATA_DIR, DB_PATH, PORT, DEMO_MODE, PUBLIC_ORIGIN
    origin = validate_public_origin(public_origin) if public_origin else ''
    DATA_DIR = Path(data_dir) if data_dir is not None else ROOT / ('datos_demo' if demo else 'datos_locales')
    DATA_DIR = DATA_DIR.resolve()
    DB_PATH = DATA_DIR / 'laboratorio.db'
    PORT, DEMO_MODE = int(port), bool(demo)
    PUBLIC_ORIGIN = origin
    if not 0 <= PORT <= 65535:
        raise ValueError('Puerto inválido.')


def utcnow():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def local_today():
    # Santo Domingo usa UTC-04:00; evita depender de tzdata en Windows.
    return datetime.now(timezone(timedelta(hours=-4))).date()


def connect():
    db = sqlite3.connect(DB_PATH, timeout=15, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys = ON')
    db.execute('PRAGMA busy_timeout = 15000')
    return db


@contextmanager
def database():
    db = connect()
    try:
        yield db
    finally:
        db.close()


def pw_hash(password, salt):
    return hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(salt), PASSWORD_ROUNDS).hex()


def verify_password(user, candidate):
    return hmac.compare_digest(pw_hash(candidate, user['salt']), user['hash'])


def effective_role(row):
    return row['access_role'] or row['role']


def session_cookie_name():
    # Los navegadores comparten cookies entre puertos del mismo equipo.
    return 'sid_demo' if DEMO_MODE else 'sid'


def session_cookie(value='', max_age=0):
    flags = f'{session_cookie_name()}={value}; HttpOnly; SameSite=Strict; Path=/; Max-Age={max_age}'
    return flags + ('; Secure' if PUBLIC_ORIGIN else '')


def public_shared_account(username):
    return bool(PUBLIC_ORIGIN and DEMO_MODE and username in ('90001', '90002', 'visitante_demo'))


def backup_before_migration():
    if not DB_PATH.exists() or not DB_PATH.stat().st_size:
        return
    with sqlite3.connect(f'file:{DB_PATH.as_posix()}?mode=ro', uri=True) as source:
        version = source.execute('PRAGMA user_version').fetchone()[0]
        if version >= SCHEMA_VERSION:
            return
        target_dir = DATA_DIR / 'backups'
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / ('antes-v1-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.db')
        with sqlite3.connect(target) as dest:
            source.backup(dest)
            if dest.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('La copia de respaldo no pasó la comprobación de integridad.')
        try:
            target.chmod(0o600)
        except OSError:
            pass


def create_backup():
    target_dir = DATA_DIR / 'backups'
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / ('respaldo-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.db')
    with database() as source:
        with sqlite3.connect(target) as destination:
            source.backup(destination)
            if destination.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('No se pudo verificar el respaldo.')
    try:
        target.chmod(0o600)
    except OSError:
        pass
    return target


def init_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    backup_before_migration()
    with database() as db:
        db.execute('PRAGMA journal_mode=WAL')
        # Las tablas originales se conservan. El rol ampliado es una columna
        # adicional para evitar reconstruir users y sus relaciones históricas.
        db.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                salt TEXT NOT NULL,
                hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('supervisor','tecnico')),
                active INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                csrf TEXT NOT NULL,
                expires INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS catalog (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL CHECK(kind IN ('marcas','voltajes','condiciones')),
                label TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                UNIQUE(kind,label)
            );
            CREATE TABLE IF NOT EXISTS records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                work_date TEXT NOT NULL, meter TEXT NOT NULL,
                brand TEXT NOT NULL, voltage TEXT NOT NULL,
                condition TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '',
                user_id INTEGER NOT NULL REFERENCES users(id),
                revision INTEGER NOT NULL, created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_records_meter ON records(meter,work_date,id);
        ''')
        columns = {r['name'] for r in db.execute('PRAGMA table_info(users)')}
        if 'access_role' not in columns:
            db.execute("ALTER TABLE users ADD COLUMN access_role TEXT CHECK(access_role IN ('tecnico','supervisor','administrador','visitante'))")
        if 'must_change' not in columns:
            db.execute('ALTER TABLE users ADD COLUMN must_change INTEGER NOT NULL DEFAULT 0')
        db.execute('UPDATE users SET access_role=role WHERE access_role IS NULL')
        if db.execute('SELECT count(*) FROM catalog').fetchone()[0] == 0:
            catalogs = json.loads((ROOT / 'catalogos.json').read_text(encoding='utf-8'))
            db.executemany('INSERT OR IGNORE INTO catalog(kind,label) VALUES(?,?)',
                           [(kind, label) for kind, labels in catalogs.items() for label in labels])
        additions = ['Bobina Extraída', 'CTs Quemados', 'CTs Cortados',
                     'Elemento Electrónico Añadido', 'Conexión Directa',
                     'Medidor en Óptimas Condiciones']
        db.executemany("INSERT OR IGNORE INTO catalog(kind,label) VALUES('condiciones',?)", [(v,) for v in additions])
        production.init_schema(db)
        if db.execute('PRAGMA user_version').fetchone()[0] < 3:
            # El supervisor del prototipo tenía autoridad administrativa total.
            # Conservar una cuenta dueña evita dejar la instalación migrada sin
            # nadie que pueda gestionar perfiles o respaldos en el modelo nuevo.
            has_admin = db.execute("SELECT 1 FROM users WHERE access_role='administrador' AND active=1").fetchone()
            if not has_admin:
                owner = db.execute("SELECT id FROM users WHERE role='supervisor' AND active=1 ORDER BY id LIMIT 1").fetchone()
                if owner:
                    db.execute("UPDATE users SET access_role='administrador' WHERE id=?", (owner['id'],))
                    production.audit(db, owner['id'], 'users', owner['id'], 'migracion_administracion',
                                     reason='Conservar la autoridad administrativa de la instalación original')
        db.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
        if db.execute('PRAGMA foreign_key_check').fetchone() is not None:
            raise RuntimeError('La migración detectó referencias inconsistentes; conservar respaldo y revisar.')


def user_public(db, row):
    return {'id': row['id'], 'username': row['username'], 'name': row['name'],
            'role': effective_role(row), 'active': bool(row['active']),
            'must_change': bool(row['must_change']),
            'activity_ids': [r[0] for r in db.execute(
                'SELECT activity_id FROM user_activities WHERE user_id=? AND enabled=1', (row['id'],))]}


def db_user_by_session(raw_cookie):
    if not raw_cookie:
        return None
    hashed = hashlib.sha256(raw_cookie.encode()).hexdigest()
    with database() as db:
        row = db.execute('''SELECT u.*,s.csrf,s.expires FROM sessions s
                            JOIN users u ON u.id=s.user_id WHERE s.token_hash=?''', (hashed,)).fetchone()
        if not row or not row['active'] or row['expires'] <= int(time.time()):
            return None
        user = user_public(db, row)
        user['csrf'] = row['csrf']
        return user


def validate_username(value):
    value = str(value or '').strip().lower()
    if not re.fullmatch(r'[a-z0-9][a-z0-9_.-]{2,34}', value):
        raise ValueError('El usuario debe tener de 3 a 35 letras, números, puntos, guiones o guion bajo.')
    return value


def validate_name(value):
    value = str(value or '').strip()
    if not value or len(value) > 90:
        raise ValueError('Introduce un nombre de hasta 90 caracteres.')
    return value


def validate_password(password, username, role):
    password = str(password or '')
    minimum = 10 if role in MANAGERS else 4
    if not minimum <= len(password) <= 128:
        raise ValueError(f'La contraseña debe tener de {minimum} a 128 caracteres.')
    if role in MANAGERS and hmac.compare_digest(password.lower(), username.lower()):
        raise ValueError('Supervisores y administradores necesitan una contraseña propia, diferente del usuario.')
    return password


def insert_user(db, username, name, role, password, must_change=0):
    salt = secrets.token_hex(16)
    old_role = 'supervisor' if role in MANAGERS else 'tecnico'
    return db.execute('''INSERT INTO users(username,name,salt,hash,role,access_role,must_change)
                         VALUES(?,?,?,?,?,?,?)''',
                      (username, name, salt, pw_hash(password, salt), old_role, role, must_change)).lastrowid


class Handler(BaseHTTPRequestHandler):
    server_version = 'LaboratorioLocal/1.0'

    def log_message(self, fmt, *args):
        print('%s - %s' % (self.address_string(), fmt % args), flush=True)

    def common_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; connect-src 'self'; font-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")

    def send_bytes(self, body, mime, status=200, headers=None):
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(body)))
        self.common_headers()
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def json(self, data, status=200, headers=None):
        self.send_bytes(json.dumps(data, ensure_ascii=False).encode(), 'application/json; charset=utf-8', status, headers)

    def fail(self, message, status=400, **details):
        self.json({'error': message, **details}, status)

    def current(self):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get('Cookie', ''))
            name = session_cookie_name()
            token = cookie[name].value if name in cookie else ''
        except Exception:
            token = ''
        return db_user_by_session(token)

    def auth(self, admin=False, csrf=False):
        user = self.current()
        if not user:
            self.fail('Inicia sesión para continuar.', 401)
            return None
        if admin and user['role'] not in MANAGERS:
            self.fail('Acceso exclusivo de supervisión y administración.', 403)
            return None
        if user['must_change'] and urlparse(self.path).path not in ('/api/password', '/api/logout', '/api/me'):
            self.fail('Cambia tu contraseña inicial para continuar.', 403, must_change=True)
            return None
        if csrf and not hmac.compare_digest(self.headers.get('X-CSRF-Token', ''), user['csrf']):
            self.fail('Verificación de seguridad fallida. Actualiza la página.', 403)
            return None
        return user

    def check_host(self):
        # El proveedor usa Host/IP internos para comprobar salud. Esta ruta no
        # ofrece información de cuentas, base de datos ni almacenamiento.
        if self.command == 'GET' and urlparse(self.path).path == '/healthz':
            return True
        port = self.server.server_port
        host = self.headers.get('Host')
        if PUBLIC_ORIGIN:
            allowed = host == urlparse(PUBLIC_ORIGIN).netloc
        else:
            allowed = host in (f'{HOST}:{port}', f'localhost:{port}')
        if not allowed:
            self.fail('Dirección del servidor no permitida.', 403)
            return False
        return True

    def check_origin(self):
        port = self.server.server_port
        allowed = (PUBLIC_ORIGIN,) if PUBLIC_ORIGIN else (None, f'http://{HOST}:{port}', f'http://localhost:{port}')
        if self.headers.get('Origin') not in allowed:
            self.fail('Origen no permitido.', 403)
            return False
        return True

    def read_json(self):
        if self.headers.get('Content-Type', '').split(';')[0].strip().lower() != 'application/json':
            raise production.ApiError('Usa una solicitud JSON.', 415)
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= MAX_JSON_BYTES:
                raise production.ApiError('La solicitud está vacía o supera el límite de 12 MB.', 413)
            data = json.loads(self.rfile.read(length).decode('utf-8'))
            if not isinstance(data, dict):
                raise ValueError()
            return data
        except (ValueError, UnicodeDecodeError):
            raise production.ApiError('Formato JSON inválido.')

    def do_GET(self):
        self._dispatch('GET')

    def do_POST(self):
        self._dispatch('POST')

    def _dispatch(self, method):
        try:
            if not self.check_host():
                return
            parsed = urlparse(self.path)
            query = {key: values[0] for key, values in parse_qs(parsed.query).items()}
            if method == 'GET':
                return self.get_route(parsed.path, query)
            if not self.check_origin():
                return
            return self.post_route(parsed.path, self.read_json())
        except production.ApiError as error:
            self.fail(str(error), error.status, **getattr(error, 'details', {}))
        except (ValueError, binascii.Error) as error:
            self.fail(str(error) or 'Datos inválidos.')
        except sqlite3.IntegrityError:
            self.fail('El registro ya existe o tiene referencias no válidas.', 409)
        except Exception:
            traceback.print_exc()
            self.fail('No se pudo completar la operación. Revisa el registro local del servidor.', 500)

    def get_route(self, path, query):
        if path == '/healthz':
            return self.json({'ok': True})
        static = {'/': ('static/index.html', 'text/html; charset=utf-8'),
                  '/app.js': ('static/app.js', 'application/javascript; charset=utf-8'),
                  '/app.css': ('static/app.css', 'text/css; charset=utf-8'),
                  '/edesur.png': ('assets/edesur.png', 'image/png')}
        if path in static:
            filename, mime = static[path]
            return self.send_bytes((ROOT / filename).read_bytes(), mime)
        if path == '/favicon.ico':
            return self.send_bytes(b'', 'image/x-icon', 204)
        if path == '/api/me':
            user = self.current()
            with database() as db:
                setup = db.execute('SELECT count(*) FROM users').fetchone()[0] == 0
            result = {'logged': bool(user), 'setup_required': setup, 'demo': DEMO_MODE,
                      'public_demo': bool(PUBLIC_ORIGIN and DEMO_MODE), 'version': VERSION}
            if user:
                result.update(csrf=user['csrf'], user={k: user[k] for k in ('id', 'username', 'name', 'role', 'must_change')})
            return self.json(result)
        user = self.auth()
        if not user:
            return
        with database() as db:
            if path == '/api/usuarios':
                if user['role'] == 'visitante':
                    raise production.ApiError('El perfil visitante solo consulta estadísticas agregadas.', 403)
                rows = db.execute('SELECT * FROM users ORDER BY name,id') if user['role'] in MANAGERS else db.execute('SELECT * FROM users WHERE id=?', (user['id'],))
                return self.json({'users': [user_public(db, row) for row in rows]})
            if path == '/api/catalogos':
                result = {kind: [] for kind in ('marcas', 'voltajes', 'condiciones')}
                for row in db.execute('SELECT kind,label FROM catalog WHERE active=1 ORDER BY kind,label'):
                    result[row['kind']].append(row['label'])
                return self.json(result)
            if path in ('/api/export.csv', '/api/export.xlsx', '/api/export.pdf'):
                table = production.export_rows(db, user, query)
                extension = path.rsplit('.', 1)[1]
                if extension == 'csv':
                    body, mime = documents.write_csv(table['headers'], table['rows']), 'text/csv; charset=utf-8'
                elif extension == 'xlsx':
                    body, mime = documents.write_xlsx(table['headers'], table['rows'], title=table['title']), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                else:
                    body, mime = documents.write_pdf(table['headers'], table['rows'], title=table['title']), 'application/pdf'
                return self.send_bytes(body, mime, headers={'Content-Disposition': f'attachment; filename="produccion-{local_today().isoformat()}.{extension}"'})
            if path in ('/api/plantilla.csv', '/api/plantilla.xlsx'):
                if user['role'] not in MANAGERS:
                    raise production.ApiError('Solo supervisión y administración pueden importar.', 403)
                activity = query.get('activity_id', 'revision')
                headers = documents.template_columns(activity)
                extension = path.rsplit('.', 1)[1]
                if extension == 'xlsx':
                    body, mime = documents.write_xlsx(headers, [], title='Plantilla de ' + activity), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                else:
                    body, mime = documents.write_csv(headers, []), 'text/csv; charset=utf-8'
                return self.send_bytes(body, mime, headers={'Content-Disposition': f'attachment; filename="plantilla-{activity}.{extension}"'})
            result = production.handle_get(db, user, path, query)
            if result is not None:
                return self.json(result)
        self.fail('Ruta no encontrada.', 404)

    def post_route(self, path, data):
        if path == '/api/setup':
            username = validate_username(data.get('username'))
            name = validate_name(data.get('name'))
            password = validate_password(data.get('password'), username, 'administrador')
            with database() as db:
                db.execute('BEGIN IMMEDIATE')
                try:
                    if db.execute('SELECT count(*) FROM users').fetchone()[0]:
                        raise production.ApiError('La configuración inicial ya se completó.', 409)
                    uid = insert_user(db, username, name, 'administrador', password)
                    production.audit(db, uid, 'users', uid, 'creacion_inicial', reason='Configuración inicial local')
                    db.execute('COMMIT')
                except Exception:
                    db.execute('ROLLBACK')
                    raise
            return self.json({'ok': True})
        if path == '/api/login':
            username = str(data.get('username', '')).strip().lower()
            password = str(data.get('password', ''))
            if not re.fullmatch(r'[a-z0-9][a-z0-9_.-]{2,34}', username) or len(password) > 128:
                raise production.ApiError('Usuario o contraseña incorrectos.', 401)
            key = (self.client_address[0], username)
            now = time.time()
            # Estas tres credenciales son botones públicos sin secreto. No
            # compartir un bloqueo por IP del proxy entre todos los evaluadores.
            # Administración y cuentas personales conservan el límite normal.
            shared = public_shared_account(username)
            with LOGIN_LOCK:
                failures = [] if shared else [value for value in LOGIN_FAILS.get(key, []) if now - value < LOGIN_WINDOW_SECONDS]
                if not shared:
                    LOGIN_FAILS[key] = failures
                remaining = max(1, math.ceil(LOGIN_WINDOW_SECONDS - (now - failures[0]))) if len(failures) >= LOGIN_MAX_FAILURES else 0
            if remaining:
                minutes, seconds = divmod(remaining, 60)
                return self.json({
                    'error': f'Demasiados intentos. Vuelve a intentarlo en {minutes} min {seconds} s.',
                    'retry_after_seconds': remaining,
                }, 429, headers={'Retry-After': str(remaining)})
            with database() as db:
                row = db.execute('SELECT * FROM users WHERE username=? AND active=1', (username,)).fetchone()
                if not row or not verify_password(row, password):
                    if not shared:
                        with LOGIN_LOCK:
                            LOGIN_FAILS.setdefault(key, []).append(now)
                    raise production.ApiError('Usuario o contraseña incorrectos.', 401)
                token, csrf = secrets.token_urlsafe(36), secrets.token_urlsafe(22)
                db.execute('DELETE FROM sessions WHERE expires<=?', (int(now),))
                db.execute('INSERT INTO sessions VALUES(?,?,?,?)', (hashlib.sha256(token.encode()).hexdigest(), row['id'], csrf, int(now) + 8 * 3600))
            with LOGIN_LOCK:
                LOGIN_FAILS.pop(key, None)
            return self.json({'ok': True}, headers={'Set-Cookie': session_cookie(token, 28800)})
        user = self.auth(csrf=True)
        if not user:
            return
        if path == '/api/logout':
            cookie = SimpleCookie()
            cookie.load(self.headers.get('Cookie', ''))
            name = session_cookie_name()
            token = cookie[name].value if name in cookie else ''
            with database() as db:
                db.execute('DELETE FROM sessions WHERE token_hash=?', (hashlib.sha256(token.encode()).hexdigest(),))
            return self.json({'ok': True}, headers={'Set-Cookie': session_cookie()})
        if path == '/api/password':
            if public_shared_account(user['username']):
                raise production.ApiError('Este acceso de evaluación es compartido y conserva su contraseña de prueba.', 403)
            password = validate_password(data.get('password'), user['username'], user['role'])
            with database() as db:
                row = db.execute('SELECT * FROM users WHERE id=?', (user['id'],)).fetchone()
                if not verify_password(row, str(data.get('current_password', ''))):
                    raise production.ApiError('La contraseña actual no coincide.', 400)
                salt = secrets.token_hex(16)
                db.execute('BEGIN IMMEDIATE')
                try:
                    db.execute('UPDATE users SET salt=?,hash=?,must_change=0 WHERE id=?', (salt, pw_hash(password, salt), user['id']))
                    db.execute('DELETE FROM sessions WHERE user_id=?', (user['id'],))
                    production.audit(db, user['id'], 'users', user['id'], 'cambio_clave', reason='Cambio por el titular')
                    db.execute('COMMIT')
                except Exception:
                    db.execute('ROLLBACK')
                    raise
            return self.json({'ok': True, 'relogin': True}, headers={'Set-Cookie': session_cookie()})
        if path == '/api/usuarios' or re.fullmatch(r'/api/usuarios/\d+/(actualizar|restablecer)', path):
            return self.manage_users(path, data, user)
        if path == '/api/backup':
            if user['role'] != 'administrador':
                raise production.ApiError('Solo administración puede generar respaldos completos.', 403)
            target = create_backup()
            with database() as db:
                production.audit(db, user['id'], 'sistema', target.name, 'respaldo',
                                 reason='Copia local consistente verificada')
            return self.json({'ok': True, 'filename': target.name,
                              'message': 'Copia verificada guardada en la carpeta backups de los datos de esta instalación.'})
        with database() as db:
            if path == '/api/catalogos':
                if user['role'] not in MANAGERS:
                    raise production.ApiError('No tienes permiso para administrar catálogos.', 403)
                kind, label = str(data.get('kind', '')), str(data.get('label', '')).strip()
                if kind not in ('marcas', 'voltajes', 'condiciones') or not label or len(label) > 110:
                    raise ValueError('Introduce un catálogo y un valor válidos.')
                db.execute('BEGIN IMMEDIATE')
                try:
                    db.execute('INSERT INTO catalog(kind,label,active) VALUES(?,?,1) ON CONFLICT(kind,label) DO UPDATE SET active=1', (kind, label))
                    production.audit(db, user['id'], 'catalog', kind, 'agregar', after={'label': label})
                    db.execute('COMMIT')
                except Exception:
                    db.execute('ROLLBACK')
                    raise
                return self.json({'ok': True})
            if path == '/api/import/preview':
                if user['role'] not in MANAGERS:
                    raise production.ApiError('La importación requiere supervisión.', 403)
                filename = str(data.get('filename', ''))
                encoded = data.get('content_base64')
                if not isinstance(encoded, str) or len(encoded) > 11 * 1024 * 1024:
                    raise ValueError('Archivo inválido o demasiado grande.')
                content = base64.b64decode(encoded, validate=True)
                data = {**data, 'rows': documents.read_table(filename, content), 'fingerprint': hashlib.sha256(content).hexdigest()}
                data.pop('content_base64', None)
            result = production.handle_post(db, user, path, data)
            if result is not None:
                return self.json(result)
        self.fail('Ruta no encontrada.', 404)

    def manage_users(self, path, data, actor):
        if actor['role'] not in MANAGERS:
            raise production.ApiError('Solo supervisión y administración gestionan accesos.', 403)
        reset_username = None
        with database() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                if path == '/api/usuarios':
                    username = validate_username(data.get('username'))
                    name = validate_name(data.get('name'))
                    role = str(data.get('role', 'tecnico'))
                    if role not in ROLES or (actor['role'] != 'administrador' and role != 'tecnico'):
                        raise production.ApiError('No puedes asignar ese perfil.', 403)
                    password = username if role == 'tecnico' else validate_password(data.get('password'), username, role)
                    uid = insert_user(db, username, name, role, password, int(role in MANAGERS))
                    production.assign_user(db, uid, data.get('activity_ids', []))
                    production.audit(db, actor['id'], 'users', uid, 'crear', after={'username': username, 'name': name, 'role': role})
                else:
                    uid = int(path.split('/')[3])
                    target = db.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
                    if not target:
                        raise production.ApiError('No se encontró el usuario.', 404)
                    role = effective_role(target)
                    if actor['role'] != 'administrador' and role != 'tecnico':
                        raise production.ApiError('Solo administración puede gestionar perfiles privilegiados.', 403)
                    if path.endswith('/restablecer'):
                        if role != 'tecnico':
                            raise production.ApiError('Este restablecimiento es exclusivo para colaboradores.', 403)
                        salt = secrets.token_hex(16)
                        db.execute('UPDATE users SET salt=?,hash=?,must_change=0 WHERE id=?', (salt, pw_hash(target['username'], salt), uid))
                        db.execute('DELETE FROM sessions WHERE user_id=?', (uid,))
                        production.audit(db, actor['id'], 'users', uid, 'restablecer_clave', reason='Restablecimiento al código de empleado')
                        reset_username = target['username']
                    else:
                        name = validate_name(data.get('name', target['name']))
                        active = data.get('active', bool(target['active']))
                        if not isinstance(active, bool):
                            raise ValueError('El estado activo debe ser verdadero o falso.')
                        if uid == actor['id'] and not active:
                            raise ValueError('No puedes desactivar tu propia sesión.')
                        if role == 'administrador' and target['active'] and not active:
                            count = db.execute("SELECT count(*) FROM users WHERE active=1 AND access_role='administrador'").fetchone()[0]
                            if count <= 1:
                                raise ValueError('Debe mantenerse al menos una cuenta administradora activa.')
                        before = user_public(db, target)
                        db.execute('UPDATE users SET name=?,active=? WHERE id=?', (name, int(active), uid))
                        if not active:
                            db.execute('DELETE FROM sessions WHERE user_id=?', (uid,))
                        if 'activity_ids' in data:
                            production.assign_user(db, uid, data['activity_ids'])
                        updated = db.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
                        production.audit(db, actor['id'], 'users', uid, 'actualizar', before=before, after=user_public(db, updated))
                db.execute('COMMIT')
            except Exception:
                db.execute('ROLLBACK')
                raise
        if reset_username:
            with LOGIN_LOCK:
                for key in list(LOGIN_FAILS):
                    if key[1] == reset_username:
                        del LOGIN_FAILS[key]
        return self.json({'ok': True, 'id': uid})


def seed_demo(admin_password=None):
    """Solo para --demo y sobre su base separada: ninguna persona real."""
    if PUBLIC_ORIGIN and not admin_password:
        raise ValueError('La demo web necesita una contraseña privada de administración.')
    password = 'LaboratorioDemo2026!' if admin_password is None else validate_password(admin_password, 'supervisor_demo', 'administrador')
    # Evitar una demo inicial parcial si falla algún registro de ejemplo.
    with database() as db, production._transaction(db):
        if db.execute('SELECT count(*) FROM users').fetchone()[0]:
            return
        admin_id = insert_user(db, 'supervisor_demo', 'Supervisión de prueba', 'administrador', password)
        techs = [insert_user(db, '90001', 'Colaborador Demo Uno', 'tecnico', '90001'),
                 insert_user(db, '90002', 'Colaboradora Demo Dos', 'tecnico', '90002')]
        insert_user(db, 'visitante_demo', 'Visita de prueba', 'visitante', 'VisitanteDemo2026!')
        activities = production.handle_get(db, {'id': admin_id, 'role': 'administrador'}, '/api/actividades', {})['activities']
        ids = [activity['id'] for activity in activities]
        for uid in techs:
            production.assign_user(db, uid, ids)
        actor = {'id': admin_id, 'username': 'supervisor_demo', 'name': 'Supervisión de prueba', 'role': 'administrador', 'active': True}
        for offset in range(9, -1, -1):
            work_date = (local_today() - timedelta(days=offset)).isoformat()
            responsible = techs[offset % 2]
            entries = [
                ('limpieza', 12 + offset, {'voltaje': '240V', 'tiempo_minutos': 40 + offset, 'condicion_visual': 'Bueno', 'sap': '1003913', 'clasificacion': 'Recuperado'}),
                ('revision', 1, {'serie': '000' + str(1000 + offset), 'marca': 'Marca de prueba', 'voltaje': '240V', 'sap': '1003913', 'condicion': 'Base Rota', 'clasificacion': 'Recuperado', 'resultado': 'No apto'}),
                ('configuracion', 5 + offset, {'tipo_configuracion': 'Prepago', 'sap': '1003913', 'marca': 'Marca de prueba', 'voltaje': '240V'}),
                ('sellado', 1, {'serie': '000' + str(2000 + offset), 'sap': '1003913', 'marca': 'Marca de prueba', 'voltaje': '240V', 'clasificacion': 'Recuperado'}),
                ('asignacion', 20 + offset, {'tipo_articulo': 'Sello', 'sap': 'SELLO-DEMO', 'destino': 'Equipo de prueba'}),
                ('recepcion', 8, {'sap': 'SAP-NUEVO-DEMO', 'numero_orden': 'ORD-DEMO-01', 'proceso': 'Recepción de prueba', 'marca': 'Marca de prueba', 'cantidad_esperada': 100}),
            ]
            for activity_id, quantity, fields in entries:
                production.handle_post(db, actor, '/api/eventos', {'activity_id': activity_id, 'work_date': work_date, 'responsible_id': responsible, 'quantity': quantity, 'data': {**fields, 'observaciones': 'Datos ficticios para probar la aplicación'}, 'operation_id': f'demo-v1-{offset}-{activity_id}', 'confirm_reentry': True})
        production.handle_post(db, actor, '/api/metas', {'responsible_id': techs[0], 'activity_id': 'limpieza', 'start_date': (local_today() - timedelta(days=15)).isoformat(), 'end_date': (local_today() + timedelta(days=15)).isoformat(), 'target': 180})


def main():
    if sys.version_info < (3, 11):
        raise SystemExit('Se necesita Python 3.11 o superior.')
    parser = argparse.ArgumentParser(description='Laboratorio de Medidas — Control de Producción local')
    parser.add_argument('--demo', action='store_true', help='Datos ficticios en una base separada de los registros normales')
    parser.add_argument('--data-dir', help='Directorio local de datos (nunca una unidad compartida)')
    parser.add_argument('--port', type=int, help='Puerto local; por defecto 8765 normal y 8766 demo')
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    port = args.port if args.port is not None else (DEFAULT_DEMO_PORT if args.demo else DEFAULT_NORMAL_PORT)
    configure(args.data_dir, port, args.demo)
    # Reservar el puerto antes de modificar la base evita migrar mientras una
    # instancia anterior sigue atendiendo e insertando revisiones antiguas.
    server = ThreadingHTTPServer((HOST, PORT), Handler, bind_and_activate=False)
    try:
        try:
            server.server_bind()
        except OSError as error:
            if error.errno in (errno.EADDRINUSE, 10048):
                raise SystemExit(f'El puerto {PORT} ya está en uso. Cierra la otra consola de la aplicación y vuelve a abrir el iniciador.') from None
            raise
        init_db()
        if args.demo:
            seed_demo()
        server.server_activate()
    except BaseException:
        server.server_close()
        raise
    url = f'http://{HOST}:{server.server_port}'
    mode = 'DEMOSTRACIÓN CON DATOS FICTICIOS' if args.demo else 'INSTALACIÓN NORMAL'
    print(f'Laboratorio de Medidas — Control de Producción {VERSION}\n{mode}\n{url}\nSolo prueba local. Ctrl+C para cerrar.', flush=True)
    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
