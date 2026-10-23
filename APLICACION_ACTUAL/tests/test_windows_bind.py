"""Port ownership regressions; all live sockets use loopback on every platform."""
from __future__ import annotations

import errno
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest import mock

APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))
import app


class ServerPortOwnershipTests(unittest.TestCase):
    def tearDown(self):
        app.configure()

    def test_windows_reserves_exclusively_before_the_inherited_bind(self):
        server = object.__new__(app.ThreadingHTTPServer)
        server.socket = mock.Mock()
        server.allow_reuse_address = True
        server.allow_reuse_port = True
        events = []
        server.socket.setsockopt.side_effect = lambda *values: events.append(('option', *values))

        def inherited_bind(instance):
            self.assertIs(instance, server)
            self.assertFalse(instance.allow_reuse_address)
            self.assertFalse(instance.allow_reuse_port)
            events.append(('bind',))

        with mock.patch.object(app.sys, 'platform', 'win32'), mock.patch.object(socket, 'SO_EXCLUSIVEADDRUSE', -5, create=True), mock.patch.object(app.BaseThreadingHTTPServer, 'server_bind', autospec=True, side_effect=inherited_bind):
            server.server_bind()
        self.assertEqual(events, [('option', socket.SOL_SOCKET, -5, 1), ('bind',)])

    def test_unix_keeps_the_standard_library_reuse_policy(self):
        server = object.__new__(app.ThreadingHTTPServer)
        server.socket = mock.Mock()
        standard_reuse = app.BaseThreadingHTTPServer.allow_reuse_address
        standard_reuse_port = app.BaseThreadingHTTPServer.allow_reuse_port
        with mock.patch.object(app.sys, 'platform', 'linux'), mock.patch.object(app.BaseThreadingHTTPServer, 'server_bind', autospec=True) as inherited:
            server.server_bind()
        inherited.assert_called_once_with(server)
        server.socket.setsockopt.assert_not_called()
        self.assertEqual(server.allow_reuse_address, standard_reuse)
        self.assertEqual(server.allow_reuse_port, standard_reuse_port)
        self.assertNotIn('allow_reuse_address', vars(server))
        self.assertNotIn('allow_reuse_port', vars(server))

    def test_second_http_server_cannot_bind_an_active_listener(self):
        # Executes the real SO_EXCLUSIVEADDRUSE branch when the CI runs on Windows.
        first = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        self.addCleanup(first.server_close)
        second = app.ThreadingHTTPServer(first.server_address, app.Handler, bind_and_activate=False)
        self.addCleanup(second.server_close)
        with self.assertRaises(OSError):
            second.server_bind()

    def test_a_closed_listener_without_active_connections_can_restart(self):
        first = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        address = first.server_address
        first.server_close()
        # No reuse override is needed once an idle exclusive listener is closed.
        second = app.ThreadingHTTPServer(address, app.Handler)
        self.addCleanup(second.server_close)
        self.assertEqual(second.server_address, address)

    def test_winsock_busy_errors_exit_before_database_migration(self):
        direct_busy = OSError(10048, 'Synthetic WSAEADDRINUSE')
        exclusive_busy = OSError(10013, 'Synthetic WSAEACCES')
        mapped_busy = OSError(errno.EACCES, 'Synthetic mapped WSAEACCES')
        mapped_busy.winerror = 10013
        for error in (direct_busy, exclusive_busy, mapped_busy):
            with self.subTest(errno=error.errno, winerror=getattr(error, 'winerror', None)), tempfile.TemporaryDirectory(prefix='laboratorio-exclusive-bind-') as directory:
                original = Path(directory) / 'laboratorio.db'
                original.write_bytes(b'Synthetic database must remain untouched before bind')
                before = original.read_bytes()
                server = mock.Mock()
                server.server_bind.side_effect = error
                arguments = ['app.py', '--data-dir', directory, '--port', '17895', '--no-browser']
                with mock.patch.object(app.sys, 'argv', arguments), mock.patch.object(app, 'ThreadingHTTPServer', return_value=server), mock.patch.object(app, 'init_db') as migrate, mock.patch.object(app, 'seed_demo') as seed:
                    with self.assertRaisesRegex(SystemExit, 'El puerto 17895 ya está en uso'):
                        app.main()
                    migrate.assert_not_called()
                    seed.assert_not_called()
                    server.server_activate.assert_not_called()
                    server.server_close.assert_called_once()
                self.assertEqual(original.read_bytes(), before)
                self.assertFalse((Path(directory) / 'backups').exists())


if __name__ == '__main__':
    unittest.main()
