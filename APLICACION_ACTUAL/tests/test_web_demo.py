"""Public demo boundary checks; requests stay on loopback with proxy headers."""
from __future__ import annotations

import hashlib
import http.client
import contextlib
import json
import secrets
import socket
import sqlite3
import sys
import tempfile
import threading
import unittest
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))
import app
import web_demo


class WebConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='laboratorio-web-settings-')
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / 'web-data'
        self.password = secrets.token_urlsafe(24)
        self.env = {'LAB_PUBLIC_ORIGIN': 'https://review.example.test',
                    'LAB_DATA_DIR': str(self.directory), 'PORT': '0',
                    'LAB_BIND_HOST': '127.0.0.1', 'LAB_ADMIN_PASSWORD': self.password}

    def tearDown(self):
        app.configure()

    def test_https_origin_is_exact_and_local_defaults_are_restored(self):
        valid = web_demo.settings_from_environment(self.env)
        self.assertEqual(valid.origin, 'https://review.example.test')
        self.assertNotIn(self.password, repr(valid))
        app.configure(self.directory, 0, True, public_origin=valid.origin)
        self.assertEqual(app.PUBLIC_ORIGIN, valid.origin)
        self.assertIn('Secure', app.session_cookie('test', 10))
        app.configure(self.directory, 0, False)
        self.assertEqual(app.PUBLIC_ORIGIN, '')
        self.assertNotIn('Secure', app.session_cookie('test', 10))
        for invalid in ('http://review.example.test', 'https://review.example.test/path',
                        'https://review.example.test?x=1', 'https://review.example.test#x',
                        'https://name:password@review.example.test',
                        'https://review.example.test\\evil', 'https://review.example.test:99999',
                        'https://bad..example.test', 'https://review.example.test?',
                        'https://review.example.test#', 'https://review.example.test\n.evil'):
            with self.subTest(origin=invalid), self.assertRaises(ValueError):
                app.validate_public_origin(invalid)

    def test_wrapper_requires_private_secret_and_separate_absolute_data_directory(self):
        for field, value in [('LAB_ADMIN_PASSWORD', ''), ('LAB_ADMIN_PASSWORD', 'short'),
                             ('LAB_ADMIN_PASSWORD', 'LaboratorioDemo2026!'),
                             ('LAB_DATA_DIR', ''), ('LAB_DATA_DIR', 'relative'),
                             ('LAB_DATA_DIR', str(APP_ROOT / 'datos_locales')),
                             ('LAB_DATA_DIR', str(APP_ROOT / 'datos_locales' / 'nested')),
                             ('LAB_DATA_DIR', str(APP_ROOT / 'datos_demo')),
                             ('LAB_DATA_DIR', str(APP_ROOT)), ('LAB_DATA_DIR', '/'),
                             ('LAB_BIND_HOST', 'other.example.test'), ('PORT', '-1')]:
            invalid = {**self.env, field: value}
            with self.subTest(field=field), self.assertRaises(ValueError):
                web_demo.settings_from_environment(invalid)
        self.assertFalse(self.directory.exists())
        fallback = {k: v for k, v in self.env.items() if k != 'LAB_PUBLIC_ORIGIN'}
        fallback['RENDER_EXTERNAL_URL'] = 'https://automatic.onrender.com'
        self.assertEqual(web_demo.settings_from_environment(fallback).origin, fallback['RENDER_EXTERNAL_URL'])

    def test_unmarked_existing_database_is_never_opened_or_migrated(self):
        self.directory.mkdir()
        database = self.directory / 'laboratorio.db'
        with contextlib.closing(sqlite3.connect(database)) as db, db:
            db.execute('CREATE TABLE private_example(value TEXT)')
            db.execute("INSERT INTO private_example VALUES('Synthetic guard sample')")
        before = hashlib.sha256(database.read_bytes()).digest()
        with self.assertRaises(ValueError):
            web_demo.prepare_data_directory(self.directory)
        self.assertEqual(hashlib.sha256(database.read_bytes()).digest(), before)
        self.assertFalse((self.directory / web_demo.MARKER).exists())

    def test_occupied_port_does_not_create_or_modify_demo_storage(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
            occupied.bind(('127.0.0.1', 0))
            occupied.listen(1)
            settings = web_demo.settings_from_environment({**self.env, 'PORT': str(occupied.getsockname()[1])})
            with self.assertRaises(OSError):
                web_demo.create_server(settings)
        self.assertFalse(self.directory.exists())


class PublicDemoHTTPTests(unittest.TestCase):
    origin = 'https://review.example.test'
    host = 'review.example.test'

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='laboratorio-public-http-')
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / 'web-data'
        self.password = secrets.token_urlsafe(24)
        self.settings = web_demo.WebSettings(self.origin, self.directory, 0, '127.0.0.1', self.password)
        self.server = web_demo.create_server(self.settings)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)

    def tearDown(self):
        app.LOGIN_FAILS.clear()

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        app.configure()

    def request(self, path, payload=None, *, host=None, origin=None, cookie=None, csrf=None, extra=None):
        headers = {'Host': host or self.host}
        if payload is not None:
            headers['Content-Type'] = 'application/json'
            if origin != 'omit':
                headers['Origin'] = origin or self.origin
        if cookie:
            headers['Cookie'] = cookie
        if csrf:
            headers['X-CSRF-Token'] = csrf
        headers.update(extra or {})
        raw = None if payload is None else json.dumps(payload).encode('utf-8')
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        try:
            connection.request('GET' if payload is None else 'POST', path, body=raw, headers=headers)
            response = connection.getresponse()
            body = response.read()
            result = json.loads(body) if 'application/json' in response.getheader('Content-Type', '') else body
            return response.status, result, dict(response.getheaders())
        finally:
            connection.close()

    def login(self, username, password):
        status, result, headers = self.request('/api/login', {'username': username, 'password': password})
        self.assertEqual(status, 200)
        cookie = headers['Set-Cookie'].split(';', 1)[0]
        status, profile, _ = self.request('/api/me', cookie=cookie)
        self.assertEqual(status, 200)
        self.assertTrue(profile['logged'])
        return cookie, profile['csrf'], profile['user'], headers

    def test_private_admin_secret_and_public_seed_survive_idempotent_initialization(self):
        status, _, _ = self.request('/api/login', {'username': 'supervisor_demo', 'password': 'LaboratorioDemo2026!'})
        self.assertEqual(status, 401)
        cookie, _, user, _ = self.login('supervisor_demo', self.password)
        self.assertEqual(user['role'], 'administrador')
        with app.database() as db:
            before = db.execute('SELECT id,username,salt,hash FROM users ORDER BY id').fetchall()
            self.assertEqual(db.execute('SELECT count(*) FROM production_events').fetchone()[0], 60)
        app.init_db()
        app.seed_demo(admin_password=secrets.token_urlsafe(24))
        with app.database() as db:
            after = db.execute('SELECT id,username,salt,hash FROM users ORDER BY id').fetchall()
            self.assertEqual([tuple(row) for row in after], [tuple(row) for row in before])
            self.assertEqual(db.execute('SELECT count(*) FROM production_events').fetchone()[0], 60)
        self.assertTrue(self.request('/api/me', cookie=cookie)[1]['logged'])
        self.login('supervisor_demo', self.password)
        for username, password, role in [('90001', '90001', 'tecnico'),
                                         ('90002', '90002', 'tecnico'),
                                         ('visitante_demo', 'VisitanteDemo2026!', 'visitante')]:
            with self.subTest(username=username):
                self.assertEqual(self.login(username, password)[2]['role'], role)

    def test_host_and_https_origin_are_exact_and_forwarded_headers_cannot_override(self):
        self.assertEqual(self.request('/api/me', host='evil.example.test')[0], 403)
        self.assertEqual(self.request('/api/me', host='127.0.0.1:'+str(self.server.server_port))[0], 403)
        login = {'username': '90001', 'password': '90001'}
        for origin in ('omit', 'http://review.example.test', 'https://evil.example.test'):
            with self.subTest(origin=origin):
                self.assertEqual(self.request('/api/login', login, origin=origin)[0], 403)
        self.assertEqual(self.request('/api/login', login, host='evil.example.test',
                                     extra={'X-Forwarded-Host': self.host, 'X-Forwarded-Proto': 'https'})[0], 403)
        self.assertEqual(self.request('/api/login', login, origin='https://evil.example.test',
                                     extra={'X-Forwarded-Origin': self.origin})[0], 403)
        self.assertEqual(self.request('/api/login', login)[0], 200)

    def test_secure_cookies_apply_to_login_logout_and_password_change(self):
        cookie, csrf, _, headers = self.login('supervisor_demo', self.password)
        for flag in ('Secure', 'HttpOnly', 'SameSite=Strict', 'Path=/'):
            self.assertIn(flag, headers['Set-Cookie'])
        replacement = secrets.token_urlsafe(24)
        status, _, headers = self.request('/api/password', {'current_password': self.password, 'password': replacement}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 200)
        self.assertIn('Secure', headers['Set-Cookie'])
        self.assertIn('Max-Age=0', headers['Set-Cookie'])
        self.assertFalse(self.request('/api/me', cookie=cookie)[1]['logged'])
        cookie, csrf, _, _ = self.login('supervisor_demo', replacement)
        status, _, headers = self.request('/api/logout', {}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 200)
        self.assertIn('Secure', headers['Set-Cookie'])
        self.assertFalse(self.request('/api/me', cookie=cookie)[1]['logged'])

    def test_shared_evaluation_passwords_cannot_be_changed_or_break_other_visitors(self):
        for username, password in [('90001', '90001'), ('90002', '90002'),
                                   ('visitante_demo', 'VisitanteDemo2026!')]:
            with self.subTest(username=username):
                cookie, csrf, _, _ = self.login(username, password)
                status, result, _ = self.request('/api/password', {'current_password': password, 'password': secrets.token_urlsafe(24)}, cookie=cookie, csrf=csrf)
                self.assertEqual(status, 403)
                self.assertIn('compartido', result['error'])
                self.login(username, password)
                self.assertTrue(self.request('/api/me', cookie=cookie)[1]['logged'])

    def test_public_button_remains_available_after_wrong_attempts_and_admin_still_limits(self):
        for _ in range(7):
            self.assertEqual(self.request('/api/login', {'username': '90001', 'password': 'Incorrect public sample'})[0], 401)
        self.login('90001', '90001')
        for _ in range(6):
            self.assertEqual(self.request('/api/login', {'username': 'supervisor_demo', 'password': 'Incorrect private sample'})[0], 401)
        status, result, headers = self.request('/api/login', {'username': 'supervisor_demo', 'password': self.password})
        self.assertEqual(status, 429)
        self.assertGreater(result['retry_after_seconds'], 0)
        self.assertIn('Retry-After', headers)

    def test_health_and_me_do_not_publish_secret_or_storage_details(self):
        local_host = '127.0.0.1:'+str(self.server.server_port)
        status, health, _ = self.request('/healthz', host=local_host)
        self.assertEqual((status, health), (200, {'ok': True}))
        self.assertEqual(self.request('/healthz', host='internal-provider:10000')[1], {'ok': True})
        self.assertEqual(self.request('/healthz', {}, host='internal-provider:10000')[0], 403)
        status, result, _ = self.request('/api/me')
        self.assertEqual(status, 200)
        self.assertTrue(result['public_demo'])
        self.assertFalse(result['setup_required'])
        serialized = json.dumps(result)
        self.assertNotIn(self.password, serialized)
        self.assertNotIn(str(self.directory), serialized)
        self.assertEqual(self.request('/laboratorio.db')[0], 401)


if __name__ == '__main__':
    unittest.main()
