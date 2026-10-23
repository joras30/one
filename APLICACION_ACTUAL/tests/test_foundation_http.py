"""Fase 1 por HTTP: acceso obligatorio, perfil, equipos y bloqueo operativo."""
from pathlib import Path
import tempfile
import unittest

from test_application import Client,HTTPFixture,app
import foundation as f


class FoundationHTTPTests(HTTPFixture,unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='laboratorio-fase1-http-');self.addCleanup(self.temp.cleanup)
        self.start_http(Path(self.temp.name));self.addCleanup(self.stop_http)
        app.configure(self.temp.name,production=True);app.init_db();self.key=f.bootstrap(app)
        self.admin=Client(self.base);self.assertEqual(self.admin.login('admin',self.key)[0],200)

    def complete(self,client,username,key):
        password='ClaveFicticiaPropia2026!'
        self.result(client,'/api/password',{'current_password':key,'password':password})
        self.assertEqual(client.login(username,password)[0],200)
        self.result(client,'/api/profile',{'full_name':'Persona ficticia '+username,'identity_number':'000-0000000-1',
            'birth_date':'1990-01-02','phone':'000-000-0000','fleet':'','position':'Puesto ficticio'})
        return password

    def create(self,actor,code,role='tecnico'):
        result=self.result(actor,'/api/usuarios',{'username':code,'name':'Persona ficticia '+code,
            'position':'Puesto ficticio','role':role,'activity_ids':[]})
        client=Client(self.base);self.assertEqual(client.login(code,result['temporary_password'])[0],200)
        self.complete(client,code,result['temporary_password'])
        return result,client

    def test_temporary_password_then_profile_are_required_before_administration(self):
        self.result(self.admin,'/api/usuarios',expected=403)
        self.result(self.admin,'/api/password',{'current_password':self.key,'password':'ClaveFicticiaPropia2026!'})
        self.admin.login('admin','ClaveFicticiaPropia2026!')
        self.assertTrue(self.result(self.admin,'/api/me')['user']['must_complete_profile'])
        self.result(self.admin,'/api/base/status',expected=403)
        self.result(self.admin,'/api/profile',{'full_name':'Maestro ficticio','identity_number':'00000000001',
            'birth_date':'1990-01-02','phone':'0000000000','fleet':'','position':'Administrador ficticio'})
        status=self.result(self.admin,'/api/base/status')
        self.assertEqual(status['phase'],1)
        self.assertFalse(self.result(self.admin,'/api/me')['user']['must_complete_profile'])

    def test_operational_writes_wait_for_phase_two_and_general_audit_is_admin_only(self):
        self.complete(self.admin,'admin',self.key)
        self.result(self.admin,'/api/eventos',{'activity_id':'revision'},expected=423)
        self.result(self.admin,'/api/sap',{'code':'FICTICIO'},expected=423)
        _,supervisor=self.create(self.admin,'sup_ficticio','supervisor')
        self.result(supervisor,'/api/auditoria',expected=403)
        self.result(supervisor,'/api/base/status',expected=403)
        self.result(supervisor,'/api/base/backup-now',{},expected=403)

    def test_supervisors_manage_their_own_team_and_reset_forces_a_new_password(self):
        self.complete(self.admin,'admin',self.key)
        _,first=self.create(self.admin,'sup_uno','supervisor')
        _,second=self.create(self.admin,'sup_dos','supervisor')
        person,tech=self.create(first,'91001')
        self.assertIn('91001',[x['username'] for x in self.result(first,'/api/usuarios')['users']])
        self.assertNotIn('91001',[x['username'] for x in self.result(second,'/api/usuarios')['users']])
        self.result(second,f"/api/usuarios/{person['id']}/restablecer",{},expected=403)
        reset=self.result(first,f"/api/usuarios/{person['id']}/restablecer",{})
        self.assertNotEqual(reset['temporary_password'],'91001')
        self.assertFalse(self.result(tech,'/api/me')['logged'])
        self.assertEqual(tech.login('91001',reset['temporary_password'])[0],200)
        self.assertTrue(self.result(tech,'/api/me')['user']['must_change'])


if __name__=='__main__':unittest.main()
