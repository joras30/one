"""Fase 1 con bases temporales, volúmenes simulados y copias físicas verificadas."""
from contextlib import closing
from datetime import datetime, timedelta
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'APLICACION_ACTUAL'))
import app
import foundation as f
import production as p


class FoundationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='laboratorio-base-v33-');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);app.configure(self.root/'principal',production=True);app.init_db()
        self.password=f.bootstrap(app)
        with app.database() as db:
            row=db.execute('SELECT * FROM users').fetchone();self.user=app.user_public(db,row)
        self.targets=[self.root/'externo-a',self.root/'externo-b']
        self.media=patch.object(f,'volume_identity',side_effect=lambda path: 1 if Path(path)==self.targets[0] else 2 if Path(path)==self.targets[1] else 0)

    def configure_backup(self):
        return f.save_backup_settings(app,self.user,{'daily_time':'18:00','targets':[str(x) for x in self.targets],'confirmed_distinct_media':True})

    def test_master_created_once_and_only_password_verifier_is_stored(self):
        self.assertIsNone(f.bootstrap(app))
        with app.database() as db:
            row=db.execute('SELECT * FROM users').fetchone()
            self.assertEqual((row['username'],row['must_change'],app.effective_role(row)),('admin',1,'administrador'))
            self.assertTrue(app.verify_password(row,self.password))
            self.assertEqual(db.execute('SELECT count(*) FROM production_events').fetchone()[0],0)
            self.assertEqual(f.setting(db,'implemented_phase'),1)
            self.assertEqual(f.setting(db,'validated_phase'),0)
        self.assertNotIn(self.password.encode(),app.DB_PATH.read_bytes())

    def test_existing_unmarked_installation_is_not_overwritten_as_production(self):
        other=self.root/'anterior';app.configure(other);app.init_db()
        with app.database() as db:app.insert_user(db,'anterior','Persona ficticia','administrador','ClaveAnteriorFicticia2026!')
        app.configure(other,production=True);app.init_db()
        with self.assertRaises(p.ApiError):f.bootstrap(app)
        with app.database() as db:self.assertEqual(db.execute('SELECT username FROM users').fetchone()[0],'anterior')

    def test_same_disk_folders_are_not_misrepresented_as_dual_physical_backup(self):
        with self.assertRaises(p.ApiError):self.configure_backup()
        with self.media:
            for paths in ([str(self.targets[0])]*2,[str(app.DATA_DIR/'copy'),str(self.targets[1])],['relative',str(self.targets[1])]):
                with self.subTest(paths=paths),self.assertRaises(p.ApiError):
                    f.save_backup_settings(app,self.user,{'daily_time':'18:00','targets':paths,'confirmed_distinct_media':True})

    def test_consistent_backup_reaches_two_external_destinations_with_matching_hashes(self):
        with self.media:
            self.configure_backup();result=f.run_backup(app,self.user)
        self.assertTrue(result['ok']);self.assertEqual(len(result['copies']),2)
        for path in [Path(result['primary']),*(Path(item['path']) for item in result['copies'])]:
            self.assertEqual(f.digest_file(path),result['sha256'])
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
                self.assertEqual(db.execute('SELECT count(*) FROM users').fetchone()[0],1)

    def test_unavailable_destination_is_incomplete_and_other_copy_still_succeeds(self):
        original=f.checked_copy
        def copy(source,target,digest):
            if target.parent==self.targets[0]:raise OSError('Unidad ficticia desconectada')
            return original(source,target,digest)
        with self.media:
            self.configure_backup()
            with patch.object(f,'checked_copy',side_effect=copy):result=f.run_backup(app,self.user)
        self.assertFalse(result['ok']);self.assertEqual(result['status'],'incompleto')
        self.assertEqual([item['ok'] for item in result['copies']],[False,True])
        self.assertTrue(Path(result['primary']).is_file())

    def test_restore_preview_then_replace_retains_safety_copy_and_revokes_sessions(self):
        with self.media:
            self.configure_backup();backup=f.run_backup(app,self.user)
            preview=f.restore_preview(app,self.user,{'path':backup['primary']})
            with app.database() as db:
                app.insert_user(db,'adicional','Persona ficticia','tecnico','ClaveFicticia2026!')
                db.execute("INSERT INTO sessions VALUES('ficticio',1,'csrf-ficticio',9999999999)")
            result=f.restore_confirm(app,self.user,{'token':preview['token'],'confirm':'RESTAURAR','reason':'Prueba sintética de restauración','password':self.password})
        self.assertTrue(result['relogin']);self.assertTrue(Path(result['safety_backup']).is_file())
        with app.database() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM users').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT count(*) FROM sessions').fetchone()[0],0)
            self.assertTrue(p.operational.audit_integrity(db,self.user)['ok'])

    def test_changed_backup_is_rejected_after_preview_without_mutating_current_database(self):
        backup=f.run_backup(app,self.user);preview=f.restore_preview(app,self.user,{'path':backup['primary']})
        with Path(backup['primary']).open('ab') as stream:stream.write(b'cambio-ficticio')
        with self.assertRaises(p.ApiError) as error:
            f.restore_confirm(app,self.user,{'token':preview['token'],'confirm':'RESTAURAR','reason':'Prueba','password':self.password})
        self.assertEqual(error.exception.status,409)
        with app.database() as db:self.assertEqual(db.execute('SELECT count(*) FROM users').fetchone()[0],1)

    def test_restore_rejects_files_outside_managed_backup_locations(self):
        with self.assertRaises(p.ApiError):f.restore_preview(app,self.user,{'path':str(app.DB_PATH)})

    def test_scheduler_runs_once_per_natural_day_and_skips_before_scheduled_time(self):
        with self.media:
            self.configure_backup();scheduler=f.BackupScheduler(app)
            moment=datetime.now(f.ZONE).replace(hour=17,minute=59)
            self.assertIsNone(scheduler.tick(moment))
            moment=moment.replace(hour=18,minute=1)
            with patch.object(app,'utcnow',return_value=moment.isoformat()):
                self.assertTrue(scheduler.tick(moment)['ok'])
                self.assertIsNone(scheduler.tick(moment+timedelta(minutes=10)))

    def test_process_lock_prevents_recovery_while_the_installation_is_running(self):
        with f.process_lock(app.DATA_DIR):
            with self.assertRaises(p.ApiError):
                with f.process_lock(app.DATA_DIR):pass

    def test_physical_recovery_resets_master_only_and_audits_without_saving_plaintext(self):
        replacement=f.reset_master(app,'Recuperación física ficticia')
        with app.database() as db:
            row=db.execute('SELECT * FROM users WHERE username=\'admin\'').fetchone()
            self.assertTrue(app.verify_password(row,replacement));self.assertFalse(app.verify_password(row,self.password))
            audit=db.execute('SELECT action,reason FROM audit_entries ORDER BY id DESC LIMIT 1').fetchone()
            self.assertEqual(audit['action'],'recuperacion_fisica_maestro')
            self.assertNotIn(replacement,json.dumps(dict(audit)))


if __name__=='__main__':unittest.main()
