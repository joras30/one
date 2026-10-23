"""LAN safeguards with synthetic accounts; every test socket binds loopback."""
from __future__ import annotations

import http.client
import errno
import json
import secrets
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))
import app


class LANConfigurationTests(unittest.TestCase):
    def tearDown(self):
        app.configure()

    def test_only_rfc1918_ipv4_can_enable_the_lan_listener(self):
        for valid in ('10.1.2.3', '172.16.1.2', '172.31.254.1', '192.168.1.20'):
            with self.subTest(value=valid):
                self.assertEqual(app.validate_lan_ip(valid), valid)
        for invalid in ('', '0.0.0.0', '127.0.0.1', '169.254.10.1', '172.15.1.1',
                        '172.32.1.1', '8.8.8.8', '192.0.2.1', '224.0.0.1',
                        '255.255.255.255', 'localhost', '192.168.1.20:8765',
                        'http://192.168.1.20', '192.168.1.20/24', '::1',
                        '::ffff:192.168.1.20', '192.168.001.20'):
            with self.subTest(value=invalid), self.assertRaises(ValueError):
                app.validate_lan_ip(invalid)

    def test_configuration_uses_exact_ip_and_restores_local_and_public_profiles(self):
        with tempfile.TemporaryDirectory(prefix='laboratorio-lan-config-') as directory:
            app.configure(directory, 8765, lan_ip='192.168.1.20')
            self.assertEqual(app.HOST, '192.168.1.20')
            self.assertEqual(app.LAN_IP, app.HOST)
            self.assertEqual(app.PUBLIC_ORIGIN, '')
            self.assertNotIn('Secure', app.session_cookie('example', 10))
            app.configure(directory, 0, True, public_origin='https://review.example.test')
            self.assertEqual(app.HOST, '127.0.0.1')
            self.assertEqual(app.LAN_IP, '')
            self.assertIn('Secure', app.session_cookie('example', 10))
            app.configure(directory)
            self.assertEqual(app.HOST, '127.0.0.1')
            self.assertEqual(app.LAN_IP, '')
            self.assertEqual(app.PUBLIC_ORIGIN, '')

    def test_lan_and_https_are_mutually_exclusive_without_changing_current_configuration(self):
        app.configure(port=8766, demo=True)
        before = (app.HOST, app.PORT, app.DB_PATH, app.PUBLIC_ORIGIN, app.LAN_IP)
        with self.assertRaises(ValueError):
            app.configure(port=8780, lan_ip='192.168.1.20', public_origin='https://review.example.test')
        self.assertEqual((app.HOST, app.PORT, app.DB_PATH, app.PUBLIC_ORIGIN, app.LAN_IP), before)

    def test_network_data_directories_are_rejected_before_any_database_is_created(self):
        for invalid in ('\\\\server\\share\\laboratorio', '//server/share/laboratorio'):
            with self.subTest(value=invalid), self.assertRaises(ValueError):
                app.configure(invalid, lan_ip='192.168.1.20')

    def test_windows_mapped_remote_drive_is_rejected(self):
        import ctypes
        fake_windows = mock.Mock()
        fake_windows.kernel32.GetDriveTypeW.return_value = 4
        with tempfile.TemporaryDirectory(prefix='laboratorio-lan-drive-') as directory:
            with mock.patch.object(app.sys, 'platform', 'win32'), mock.patch.object(ctypes, 'windll', fake_windows, create=True):
                with self.assertRaises(ValueError):
                    app.configure(directory, lan_ip='192.168.1.20')
            self.assertFalse((Path(directory) / 'laboratorio.db').exists())

    def test_cli_binds_only_the_selected_ip_before_modifying_a_database(self):
        server = mock.Mock()
        server.server_bind.side_effect = OSError(errno.EADDRNOTAVAIL, 'Synthetic unassigned IP')
        with tempfile.TemporaryDirectory(prefix='laboratorio-lan-cli-') as directory:
            arguments = ['app.py', '--lan-ip', '192.168.1.20', '--data-dir', directory, '--no-browser']
            with mock.patch.object(app.sys, 'argv', arguments), mock.patch.object(app, 'ThreadingHTTPServer', return_value=server) as constructor, mock.patch.object(app, 'init_db') as migrate:
                with self.assertRaisesRegex(SystemExit, 'no está asignada'):
                    app.main()
                constructor.assert_called_once_with(('192.168.1.20', 8765), app.Handler, bind_and_activate=False)
                migrate.assert_not_called()
                server.server_close.assert_called_once()
            self.assertFalse((Path(directory) / 'laboratorio.db').exists())


class LANHTTPTests(unittest.TestCase):
    """Exercise real guards over loopback while presenting the configured LAN host."""
    ip = '192.168.1.20'

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='laboratorio-lan-http-')
        self.addCleanup(self.temp.cleanup)
        app.configure(self.temp.name, 0, lan_ip=self.ip)
        app.init_db()
        app.LOGIN_FAILS.clear()
        self.server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.port = self.server.server_port
        self.host = f'{self.ip}:{self.port}'
        self.origin = f'http://{self.host}'

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        app.configure()

    def request(self, path, payload=None, *, host=None, origin='default', cookie=None, csrf=None):
        headers = {'Host': host or self.host}
        if payload is not None:
            headers['Content-Type'] = 'application/json'
            if origin != 'omit':
                headers['Origin'] = self.origin if origin == 'default' else origin
        if cookie:
            headers['Cookie'] = cookie
        if csrf:
            headers['X-CSRF-Token'] = csrf
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=10)
        try:
            connection.request('POST' if payload is not None else 'GET', path,
                               body=None if payload is None else json.dumps(payload).encode(), headers=headers)
            response = connection.getresponse()
            body = response.read()
            result = json.loads(body) if 'application/json' in response.getheader('Content-Type', '') else body
            return response.status, result, dict(response.getheaders())
        finally:
            connection.close()

    def setup_account(self):
        password = secrets.token_urlsafe(20)
        status, _, _ = self.request('/api/setup', {'username': 'admin_lan', 'name': 'Administración de prueba', 'password': password})
        self.assertEqual(status, 200)
        status, _, headers = self.request('/api/login', {'username': 'admin_lan', 'password': password})
        self.assertEqual(status, 200)
        cookie = headers['Set-Cookie'].split(';', 1)[0]
        self.assertIn('HttpOnly', headers['Set-Cookie'])
        self.assertIn('SameSite=Strict', headers['Set-Cookie'])
        self.assertNotIn('Secure', headers['Set-Cookie'])
        status, profile, _ = self.request('/api/me', cookie=cookie)
        self.assertEqual(status, 200)
        return cookie, profile['csrf']

    def test_lan_host_is_exact_and_never_trusts_other_addresses(self):
        status, _, _ = self.request('/')
        self.assertEqual(status, 200)
        for host in (f'localhost:{self.port}', f'127.0.0.1:{self.port}',
                     f'192.168.1.21:{self.port}', self.ip,
                     f'{self.ip}.example.test:{self.port}', f'{self.ip}:{self.port + 1}'):
            with self.subTest(host=host):
                self.assertEqual(self.request('/', host=host)[0], 403)

    def test_wrong_or_absent_origin_cannot_create_the_initial_account(self):
        data = {'username': 'admin_lan', 'name': 'Persona de prueba', 'password': secrets.token_urlsafe(20)}
        for origin in ('omit', 'null', 'http://evil.example.test',
                       f'http://localhost:{self.port}', f'https://{self.host}',
                       self.origin + '.evil', self.origin + '/'):
            with self.subTest(origin=origin):
                self.assertEqual(self.request('/api/setup', data, origin=origin)[0], 403)
        with app.database() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM users').fetchone()[0], 0)
        self.assertEqual(self.request('/api/setup', data)[0], 200)

    def test_lan_keeps_authentication_csrf_and_private_storage_guards(self):
        cookie, csrf = self.setup_account()
        self.assertEqual(self.request('/api/eventos')[0], 401)
        value = {'kind': 'voltajes', 'label': '480V'}
        self.assertEqual(self.request('/api/catalogos', value, cookie=cookie)[0], 403)
        self.assertEqual(self.request('/api/catalogos', value, cookie=cookie, csrf=csrf)[0], 200)
        self.assertEqual(self.request('/api/catalogos', value, cookie=cookie, csrf=csrf, origin='http://evil.example.test')[0], 403)
        for path in ('/datos_locales/laboratorio.db', '/laboratorio.db', '/app.py', '/production.py', '/.env'):
            with self.subTest(path=path):
                self.assertEqual(self.request(path, cookie=cookie)[0], 404)


if __name__ == '__main__':
    unittest.main()
