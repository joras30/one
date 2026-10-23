"""Preferencias de avatar: autenticación, persistencia y permisos sin datos reales."""
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from test_application import Client, HTTPFixture, app


class AvatarHTTPTests(HTTPFixture, unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='laboratorio-avatar-')
        self.addCleanup(self.temp.cleanup)
        self.start_http(Path(self.temp.name))
        self.addCleanup(self.stop_http)
        self.admin = Client(self.base)
        self.result(self.admin, '/api/setup', {'username': 'avatar_admin',
            'name': 'Administración ficticia', 'password': 'ClaveAvatarSintetica2026!'})
        self.assertEqual(self.admin.login('avatar_admin', 'ClaveAvatarSintetica2026!')[0], 200)

    def tech(self):
        self.result(self.admin, '/api/usuarios', {'username': '91001', 'name': 'Técnico ficticio',
            'role': 'tecnico', 'activity_ids': ['revision']})
        client = Client(self.base)
        self.assertEqual(client.login('91001', '91001')[0], 200)
        return client

    def test_palette_is_own_preference_and_cannot_change_role_or_other_user(self):
        tech = self.tech()
        self.assertEqual(self.result(tech, '/api/avatar')['color'], 'azul')
        self.assertEqual(self.result(self.admin, '/api/avatar')['color'], 'violeta')
        selected = self.result(tech, '/api/avatar', {'color': 'verde'})
        self.assertEqual((selected['color'], selected['role']), ('verde', 'tecnico'))
        self.assertEqual(self.result(self.admin, '/api/avatar')['color'], 'violeta')
        self.assertEqual(self.result(tech, '/api/me')['user']['avatar_color'], 'verde')
        for invalid in ({'color': 'rojo'}, {'color': []}, {'color': 'azul', 'role': 'administrador'},
                        {'color': 'azul', 'user_id': 1}):
            self.result(tech, '/api/avatar', invalid, expected=400)
        self.assertEqual(self.result(tech, '/api/avatar')['color'], 'verde')
        self.assertEqual(self.result(tech, '/api/me')['user']['role'], 'tecnico')

    def test_avatar_requires_session_and_csrf_and_updates_are_audited(self):
        self.result(Client(self.base), '/api/avatar', expected=401)
        self.result(self.admin, '/api/avatar', {'color': 'verde'}, csrf=False, expected=403)
        self.assertEqual(self.result(self.admin, '/api/avatar')['color'], 'violeta')
        self.result(self.admin, '/api/avatar', {'color': 'naranja'})
        entries = self.result(self.admin, '/api/auditoria')['entries']
        change = next(entry for entry in entries if entry['entity'] == 'avatar')
        self.assertEqual(change['after'], {'color': 'naranja'})
        self.assertTrue(self.result(self.admin, '/api/auditoria/integridad')['ok'])

    def test_palette_survives_initialization_and_backup_without_changing_accounts(self):
        with app.database() as db:
            original = [tuple(row) for row in db.execute('SELECT * FROM users ORDER BY id')]
        self.result(self.admin, '/api/avatar', {'color': 'azul'})
        app.init_db()
        self.assertEqual(self.result(self.admin, '/api/avatar')['color'], 'azul')
        with app.database() as db:
            self.assertEqual(original, [tuple(row) for row in db.execute('SELECT * FROM users ORDER BY id')])
        path = app.create_backup()
        with closing(sqlite3.connect(path)) as saved:
            self.assertEqual(saved.execute('SELECT color FROM user_avatar_preferences').fetchall(), [('azul',)])
            self.assertEqual(saved.execute('PRAGMA integrity_check').fetchone()[0], 'ok')


if __name__ == '__main__':
    unittest.main()
