"""Base local V33, fase 1. Sin servicios externos ni cambios al histórico."""
from __future__ import annotations

from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone, date
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import sqlite3
import threading
import time
from urllib.parse import quote

import production as p

REQUEST_LOCK = threading.RLock()
ZONE = timezone(timedelta(hours=-4))
RESTORE_PREVIEWS = {}
PROFILE_FIELDS = ('full_name', 'identity_number', 'birth_date', 'phone', 'fleet', 'position')
ALLOWED_PHASE_ONE_POSTS = {'/api/password', '/api/logout', '/api/avatar', '/api/usuarios', '/api/backup'}


def init_schema(db):
    db.executescript('''
        CREATE TABLE IF NOT EXISTS installation_settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS employee_profiles(
            user_id INTEGER PRIMARY KEY REFERENCES users(id),full_name TEXT NOT NULL DEFAULT '',
            identity_number TEXT NOT NULL DEFAULT '',birth_date TEXT NOT NULL DEFAULT '',
            phone TEXT NOT NULL DEFAULT '',fleet TEXT NOT NULL DEFAULT '',position TEXT NOT NULL DEFAULT '',
            completed INTEGER NOT NULL DEFAULT 0,updated_at TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS backup_runs(
            id INTEGER PRIMARY KEY,started_at TEXT NOT NULL,finished_at TEXT NOT NULL,
            source TEXT NOT NULL,primary_path TEXT NOT NULL,digest TEXT NOT NULL,
            status TEXT NOT NULL,copies_json TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS user_supervisors(
            user_id INTEGER PRIMARY KEY REFERENCES users(id),supervisor_id INTEGER NOT NULL REFERENCES users(id));
    ''')


def setting(db, key, default=None):
    row = db.execute('SELECT value FROM installation_settings WHERE key=?', (key,)).fetchone()
    return json.loads(row[0]) if row else default


def put_setting(db, key, value):
    db.execute('INSERT INTO installation_settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
               (key, json.dumps(value, ensure_ascii=False)))


def administrator(user):
    if user['role'] != 'administrador':
        raise p.ApiError('Esta función es exclusiva de Administración.', 403)


def supervisor_id(db, user_id):
    row = db.execute('SELECT supervisor_id FROM user_supervisors WHERE user_id=?', (user_id,)).fetchone()
    return row[0] if row else None


def assign_team(db, actor, user_id, data):
    import phase2
    selected = data.get('supervisor_id', actor['id'] if actor['role']=='supervisor' else None) if phase2.enabled(db) else actor['id'] if actor['role']=='supervisor' else data.get('supervisor_id')
    if selected not in (None, ''):
        selected = p._integer(selected, 'Supervisor', 1, 2**63 - 1)
        person = db.execute('SELECT access_role,active FROM users WHERE id=?', (selected,)).fetchone()
        if not person or not person['active'] or person['access_role'] != 'supervisor':
            raise p.ApiError('Selecciona un supervisor activo.')
        db.execute('INSERT INTO user_supervisors VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET supervisor_id=excluded.supervisor_id', (user_id, selected))
    elif (actor['role'] == 'administrador' or phase2.enabled(db)) and 'supervisor_id' in data:
        db.execute('DELETE FROM user_supervisors WHERE user_id=?', (user_id,))


def profile(db, user_id):
    row = db.execute('SELECT * FROM employee_profiles WHERE user_id=?', (user_id,)).fetchone()
    return dict(row) if row else {'user_id': user_id, **{key: '' for key in PROFILE_FIELDS}, 'completed': False}


def bootstrap(app):
    """Devuelve una clave temporal SOLO al crear la primera cuenta; no la persiste."""
    with app.database() as db, p._transaction(db):
        if db.execute('SELECT count(*) FROM users').fetchone()[0]:
            environment = setting(db, 'environment')
            if environment != 'production':
                raise p.ApiError('Esta carpeta contiene una instalación anterior. Usa una carpeta nueva para iniciar producción desde cero; conserva la anterior.', 409)
            return None
        password = secrets.token_urlsafe(18)
        uid = app.insert_user(db, 'admin', 'Administrador Maestro', 'administrador', password, must_change=1)
        put_setting(db, 'environment', 'production')
        put_setting(db, 'master_user_id', uid)
        put_setting(db, 'implemented_phase', 1)
        put_setting(db, 'validated_phase', 0)
        p.audit(db, uid, 'instalacion', uid, 'administrador_maestro',
                after={'username': 'admin', 'phase': 1}, reason='Primer inicio local; clave temporal mostrada una sola vez')
    return password


@contextmanager
def process_lock(directory):
    directory = Path(directory);directory.mkdir(parents=True, exist_ok=True)
    handle = (directory / '.servidor.lock').open('a+b')
    if handle.tell() == 0:
        handle.write(b'0');handle.flush()
    handle.seek(0)
    try:
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise p.ApiError('La instalación está abierta. Ciérrala en la PC principal antes de continuar.', 409) from None
        yield
    finally:
        handle.close()


def reset_master(app, reason):
    """Solo lo llama el comando físico de recuperación, nunca una ruta HTTP."""
    reason = p._text(reason, 'Motivo de recuperación', 1500, True)
    with app.database() as db, p._transaction(db):
        uid = setting(db, 'master_user_id')
        row = db.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone() if uid else None
        if not row or app.effective_role(row) != 'administrador':
            raise p.ApiError('No se encontró la cuenta maestra de esta instalación.')
        password, salt = secrets.token_urlsafe(18), secrets.token_hex(16)
        db.execute('UPDATE users SET salt=?,hash=?,must_change=1,active=1 WHERE id=?',
                   (salt, app.pw_hash(password, salt), uid))
        db.execute('DELETE FROM sessions WHERE user_id=?', (uid,))
        p.audit(db, uid, 'users', uid, 'recuperacion_fisica_maestro', reason=reason)
    return password


def save_profile(app, user, data):
    values = {key: p._text(data.get(key), key, 150, key != 'fleet') for key in PROFILE_FIELDS}
    values['full_name'] = app.validate_name(values['full_name'])
    born = date.fromisoformat(p._date(values['birth_date'], 'Fecha de nacimiento'))
    if born >= datetime.now(ZONE).date():
        raise p.ApiError('La fecha de nacimiento debe ser anterior a hoy.')
    if not re.fullmatch(r'[0-9 -]{5,30}', values['identity_number']):
        raise p.ApiError('Escribe la cédula como texto, con sus ceros y guiones.')
    if not re.fullmatch(r'[0-9+() .-]{7,35}', values['phone']):
        raise p.ApiError('Escribe un teléfono válido, incluido el prefijo si corresponde.')
    with app.database() as db, p._transaction(db):
        before = profile(db, user['id'])
        db.execute('''INSERT INTO employee_profiles(user_id,full_name,identity_number,birth_date,phone,fleet,position,completed,updated_at)
            VALUES(?,?,?,?,?,?,?,1,?) ON CONFLICT(user_id) DO UPDATE SET full_name=excluded.full_name,
            identity_number=excluded.identity_number,birth_date=excluded.birth_date,phone=excluded.phone,
            fleet=excluded.fleet,position=excluded.position,completed=1,updated_at=excluded.updated_at''',
            (user['id'], *(values[key] for key in PROFILE_FIELDS), app.utcnow()))
        db.execute('UPDATE users SET name=? WHERE id=?', (values['full_name'], user['id']))
        # Los datos personales se consultan en la ficha; la auditoría identifica
        # qué campos cambiaron sin duplicar números de cédula ni teléfonos.
        changed = [key for key in PROFILE_FIELDS if before.get(key) != values[key]]
        p.audit(db, user, 'perfil', user['id'], 'actualizar', after={'fields': changed, 'completed': True})
    return {'ok': True, 'profile': {**values, 'completed': True}}


def backup_settings(db):
    return setting(db, 'backup', {'daily_time': '18:00', 'targets': [], 'confirmed_distinct_media': False})


def volume_identity(path):
    path = Path(path).resolve()
    while not path.exists() and path != path.parent:
        path = path.parent
    return os.stat(path).st_dev


def validate_targets(data_dir, targets):
    if not isinstance(targets, list) or len(targets) not in (1, 2) or not all(isinstance(x, str) and x.strip() for x in targets):
        raise p.ApiError('Configura una o dos carpetas de respaldo, por ejemplo en las unidades de red de la operativa.')
    roots = []
    for raw in targets:
        candidate = Path(raw.strip()).expanduser()
        if not candidate.is_absolute():
            raise p.ApiError('Cada destino debe ser una ruta absoluta de la PC principal.')
        candidate = candidate.resolve()
        if candidate == Path(candidate.anchor) or candidate == Path(data_dir).resolve() or candidate.is_relative_to(Path(data_dir).resolve()):
            raise p.ApiError('Usa una carpeta dedicada de respaldo fuera de la carpeta de datos.')
        roots.append(candidate)
    if len(roots) == 2 and (roots[0] == roots[1] or roots[0].is_relative_to(roots[1]) or roots[1].is_relative_to(roots[0])):
        raise p.ApiError('Elige carpetas diferentes, sin colocar una dentro de la otra.')
    return roots


def save_backup_settings(app, user, data):
    administrator(user)
    hour = str(data.get('daily_time', ''))
    if not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]', hour):
        raise p.ApiError('Elige una hora diaria entre 00:00 y 23:59.')
    roots = validate_targets(app.DATA_DIR, data.get('targets'))
    for target in roots:
        probe = target / ('.prueba-' + secrets.token_hex(8))
        try:
            target.mkdir(parents=True, exist_ok=True)
            with probe.open('xb') as stream:
                stream.write(b'Laboratorio respaldo');stream.flush();os.fsync(stream.fileno())
        except OSError as error:
            raise p.ApiError(f'No se pudo escribir en {target}. Comprueba que la unidad esté conectada y que tu usuario de Windows tenga permiso para crear archivos. Detalle: {error}') from error
        finally:
            try:
                probe.unlink(missing_ok=True)
            except OSError:
                pass
    clean = {'daily_time': hour, 'targets': [str(x) for x in roots], 'policy': 'carpetas_operativas'}
    with app.database() as db, p._transaction(db):
        put_setting(db, 'backup', clean)
        p.audit(db, user, 'backup', 'configuracion', 'configurar_carpetas', after=clean)
    return {'ok': True, 'settings': clean}


def digest_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def checked_copy(source, target, digest):
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + '.' + secrets.token_hex(6) + '.tmp')
    try:
        with Path(source).open('rb') as src, temp.open('xb') as dest:
            shutil.copyfileobj(src, dest);dest.flush();os.fsync(dest.fileno())
        if digest_file(temp) != digest:
            raise p.ApiError('La copia no coincide con su huella de integridad.')
        try:
            temp.chmod(0o600)
        except OSError:
            pass
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)


def run_backup(app, actor=None, source='manual'):
    with REQUEST_LOCK:
        started = app.utcnow()
        primary = app.create_backup()
        digest = digest_file(primary)
        with app.database() as db:
            cfg = backup_settings(db)
        copies = []
        for raw in cfg['targets']:
            try:
                # Cada carpeta se copia y verifica por separado, incluso cuando
                # pertenece al mismo servidor que otra carpeta configurada.
                target = validate_targets(app.DATA_DIR, [raw])[0] / primary.name
                checked_copy(primary, target, digest)
                copies.append({'path': str(target), 'ok': True})
            except Exception as error:
                copies.append({'path': raw, 'ok': False, 'error': str(error)})
        status = 'correcto' if copies and all(x['ok'] for x in copies) else 'incompleto'
        with app.database() as db, p._transaction(db):
            cursor = db.execute('''INSERT INTO backup_runs(started_at,finished_at,source,primary_path,digest,status,copies_json)
                VALUES(?,?,?,?,?,?,?)''', (started, app.utcnow(), source, str(primary), digest, status, json.dumps(copies)))
            p.audit(db, actor, 'backup', cursor.lastrowid, 'crear_respaldo', after={'status': status, 'copies': copies, 'sha256': digest})
        return {'ok': status == 'correcto', 'status': status, 'primary': str(primary), 'sha256': digest, 'copies': copies}


def backup_status(app, user):
    administrator(user)
    with app.database() as db:
        rows = db.execute('SELECT * FROM backup_runs ORDER BY id DESC LIMIT 30').fetchall()
        known = {row['primary_path']: row for row in db.execute('SELECT primary_path,started_at,source FROM backup_runs')}
        files = []
        for file in (app.DATA_DIR / 'backups').glob('*.db'):
            if file.is_symlink():
                continue
            run = known.get(str(file))
            created = datetime.fromisoformat(run['started_at'].replace('Z', '+00:00')) if run else datetime.fromtimestamp(file.stat().st_mtime, timezone.utc)
            files.append({'name': file.name, 'path': str(file), 'bytes': file.stat().st_size,
                          'created_at': created.isoformat(), 'source': run['source'] if run else 'sin_tipo',
                          '_timestamp': created.timestamp()})
        files.sort(key=lambda item: (item['_timestamp'], item['name']), reverse=True)
        for index, file in enumerate(files):
            file.pop('_timestamp');file['latest'] = index == 0
        return {'settings': backup_settings(db), 'local_directory': str(app.DATA_DIR / 'backups'),
                'runs': [{**dict(row), 'copies': json.loads(row['copies_json'])} for row in rows],
                'files': files[:50],
                'timezone': 'America/Santo_Domingo (UTC−04:00)',
                'note': 'Correcto significa que se verificaron las carpetas configuradas. No certifica que estén en discos físicos distintos. La PC y la aplicación deben estar encendidas y los destinos accesibles.'}


def readonly_uri(path):
    value = path.as_posix()
    # Empty URI authority keeps Windows UNC paths as a filesystem path.
    return 'file:' + ('//' if value.startswith('//') else '') + quote(value, safe='/:') + '?mode=ro'


def restore_preview(app, user, data):
    administrator(user)
    source = Path(p._text(data.get('path'), 'Ruta del respaldo', 2000, True)).resolve()
    with app.database() as db:
        roots = [app.DATA_DIR / 'backups', *(Path(x) for x in backup_settings(db)['targets'])]
    if not any(source.is_relative_to(root.resolve()) for root in roots) or source.suffix.lower() != '.db' or not source.is_file():
        raise p.ApiError('Elige un archivo .db de la carpeta local de respaldos o de una carpeta de respaldo configurada.')
    with source.open('rb') as stream:
        if stream.read(16) != b'SQLite format 3\x00':
            raise p.ApiError('El archivo no es un respaldo SQLite válido.')
    with closing(sqlite3.connect(readonly_uri(source), uri=True)) as saved:
        if saved.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or saved.execute('PRAGMA foreign_key_check').fetchone():
            raise p.ApiError('El respaldo no pasó la verificación de integridad.')
        tables = {x[0] for x in saved.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'users', 'production_events', 'installation_settings'} <= tables or setting(saved, 'environment') != 'production':
            raise p.ApiError('Selecciona un respaldo de esta instalación de producción. Una demo no se restaura sobre producción.')
        if saved.execute('PRAGMA user_version').fetchone()[0] != app.SCHEMA_VERSION:
            raise p.ApiError('El esquema del respaldo necesita una revisión de migración antes de restaurar.')
        if not saved.execute("SELECT 1 FROM users WHERE active=1 AND access_role='administrador'").fetchone():
            raise p.ApiError('El respaldo no conserva una cuenta administradora activa.')
        counts = {table: saved.execute('SELECT count(*) FROM ' + table).fetchone()[0]
                  for table in ('users', 'production_events', 'audit_entries')}
    token = secrets.token_urlsafe(24)
    RESTORE_PREVIEWS[token] = {'user_id': user['id'], 'path': source, 'sha256': digest_file(source),
                              'expires': time.monotonic() + 600, 'counts': counts}
    return {'token': token, 'counts': counts, 'sha256': RESTORE_PREVIEWS[token]['sha256'],
            'message': 'Reemplazará la base actual. Se crea una copia de seguridad previa y se cierran las sesiones.'}


def restore_confirm(app, user, data):
    administrator(user)
    preview = RESTORE_PREVIEWS.get(str(data.get('token', '')))
    if not preview or preview['user_id'] != user['id'] or preview['expires'] < time.monotonic():
        raise p.ApiError('La vista previa venció. Verifica el respaldo nuevamente.', 409)
    if data.get('confirm') != 'RESTAURAR':
        raise p.ApiError('Escribe RESTAURAR para confirmar el reemplazo de la base.')
    reason = p._text(data.get('reason'), 'Motivo de restauración', 1500, True)
    with app.database() as db:
        row = db.execute('SELECT * FROM users WHERE id=?', (user['id'],)).fetchone()
        if not app.verify_password(row, str(data.get('password', ''))):
            raise p.ApiError('La contraseña de administración no coincide.', 403)
    if digest_file(preview['path']) != preview['sha256']:
        raise p.ApiError('El respaldo cambió después de verificarlo. Crea otra vista previa.', 409)
    with app.database() as db:was_phase_two=setting(db,'implemented_phase',1)>=2
    safety = run_backup(app, user, 'antes_restauracion')
    with app.database() as db:
        db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    for suffix in ('-wal', '-shm'):
        Path(str(app.DB_PATH) + suffix).unlink(missing_ok=True)
    try:
        checked_copy(preview['path'], app.DB_PATH, preview['sha256'])
        app.init_db()
        if was_phase_two:
            import phase2
            phase2.install(app)
        with app.database() as db, p._transaction(db):
            db.execute('DELETE FROM sessions')
            # El usuario anterior puede no existir en la copia: la identidad del
            # iniciador se conserva como referencia de texto auditada.
            master = setting(db, 'master_user_id')
            p.audit(db, master, 'instalacion', 'base', 'restauracion',
                    after={'source_sha256': preview['sha256'], 'requested_by': user['username'],
                           'safety_backup': safety['primary']}, reason=reason)
    except Exception:
        checked_copy(Path(safety['primary']), app.DB_PATH, safety['sha256'])
        app.init_db()
        raise
    RESTORE_PREVIEWS.clear()
    return {'ok': True, 'relogin': True, 'safety_backup': safety['primary']}


class BackupScheduler:
    def __init__(self, app):
        self.app = app;self.stop_event = threading.Event();self.last_attempt = 0
        self.thread = threading.Thread(target=self.run, daemon=True, name='respaldo-diario')

    def start(self):
        self.thread.start()

    def close(self):
        self.stop_event.set();self.thread.join(timeout=2)

    def tick(self, instant=None):
        current = instant or datetime.now(ZONE)
        with self.app.database() as db:
            cfg = backup_settings(db)
            last = db.execute("SELECT started_at FROM backup_runs WHERE status='correcto' AND source='automatico' ORDER BY id DESC LIMIT 1").fetchone()
        if len(cfg['targets']) not in (1, 2):
            return None
        hour, minute = map(int, cfg['daily_time'].split(':'))
        due = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if current < due:
            due -= timedelta(days=1)
        if last and datetime.fromisoformat(last[0].replace('Z', '+00:00')).astimezone(ZONE) >= due:
            return None
        if self.last_attempt and time.monotonic() - self.last_attempt < 300:
            return None
        self.last_attempt = time.monotonic()
        return run_backup(self.app, source='automatico')

    def run(self):
        while not self.stop_event.is_set():
            try:
                with REQUEST_LOCK:
                    self.tick()
            except Exception:
                # No escribir credenciales ni datos personales en la consola.
                print('El respaldo automático necesita revisión en Administración > Respaldos.', flush=True)
            self.stop_event.wait(30)
