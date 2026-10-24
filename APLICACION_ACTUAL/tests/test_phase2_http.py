"""Permisos HTTP y migración de fase 2 en loopback y con personal ficticio."""
from pathlib import Path
import base64
import tempfile
import unittest
from test_application import Client,HTTPFixture,app
import phase2 as q

class PhaseTwoHTTPTests(HTTPFixture,unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.start_http(Path(self.temp.name));self.addCleanup(self.stop_http)
        app.configure(self.temp.name,production=True);app.init_db();self.key=app.foundation.bootstrap(app);q.install(app)
        self.admin=Client(self.base);self.admin.login('admin',self.key);self.complete(self.admin,'admin',self.key)
    def complete(self,c,code,key):
        self.result(c,'/api/password',{'current_password':key,'password':'ClavePersonaFicticia2026!'})
        c.login(code,'ClavePersonaFicticia2026!')
        self.result(c,'/api/profile',{'full_name':'Persona ficticia '+code,'identity_number':'00000000001','birth_date':'1990-01-01','phone':'0000000000','fleet':'','position':'Puesto ficticio'})
    def person(self,code,role='tecnico',actor=None,**kw):
        row=self.result(actor or self.admin,'/api/usuarios',{'username':code,'name':'Persona ficticia '+code,'role':role,'position':'Puesto ficticio',**kw})
        c=Client(self.base);c.login(code,row['temporary_password']);self.complete(c,code,row['temporary_password']);return row,c
    def test_phase_one_validation_is_preserved_and_own_profile_is_private(self):
        me=self.result(self.admin,'/api/me');self.assertEqual((me['delivered_phase'],me['validated_phase']),(2,1))
        first,c=self.person('91001');second,other=self.person('91002')
        self.result(c,'/api/p2/personal',expected=403)
        self.result(c,f"/api/p2/personal/{second['id']}",expected=403)
        self.assertEqual(self.result(c,f"/api/p2/personal/{first['id']}")['person']['profile']['phone'],'0000000000')
        sup,s=self.person('supervisor_uno','supervisor');sup2,s2=self.person('supervisor_dos','supervisor')
        self.result(self.admin,f"/api/usuarios/{second['id']}/actualizar",{'name':'Persona ficticia 91002','supervisor_id':sup2['id'],'active':True})
        self.assertEqual(self.result(s,f"/api/p2/personal/{second['id']}")['person']['profile']['identity_number'],'00000000001')
        self.assertIn(second['id'],[p['id'] for p in self.result(s,'/api/p2/personal')['people']])
        self.result(s,f"/api/usuarios/{second['id']}/restablecer",{})
        self.result(s,'/api/p2/assignment',{'user_id':second['id'],'activity_id':'revision','permissions':['capturar'],'reason':'Cobertura ficticia'})
    def test_photo_belongs_to_session_and_requires_authorized_profile_access(self):
        first,c=self.person('91001');second,other=self.person('91002')
        data='iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jZQ0AAAAASUVORK5CYII='
        self.result(c,'/api/p2/photo',{'content':data})
        person=self.result(self.admin,f"/api/p2/personal/{first['id']}")['person'];self.assertTrue(person['photo'].startswith('data:image/png;base64,'))
        self.result(other,f"/api/p2/personal/{first['id']}",expected=403)
        self.result(c,'/api/p2/photo',{'content':base64.b64encode(b'<svg/>').decode()},expected=400)
        self.result(c,'/api/p2/photo',{'content':data},csrf=False,expected=403)
    def test_catalog_confirmation_is_admin_only_and_without_it_capture_is_blocked(self):
        first,c=self.person('91001');sup,s=self.person('supervisor_uno','supervisor')
        self.result(s,'/api/p2/catalog/ready',{},expected=403)
        self.result(s,'/api/p2/article',{'code':'001','valuation':'Nuevo','description':'Ficticio'},expected=403)
        self.result(self.admin,'/api/p2/assignment',{'user_id':first['id'],'activity_id':'revision','permissions':['capturar'],'reason':'Prueba ficticia'})
        payload={'activity_id':'revision','work_date':'2026-10-24','operation_id':'http-p2-1','data':{'serie':'00001','marca':'Marca ficticia','voltaje':'240V','condicion':'Condición ficticia'}}
        for kind,label in [('marcas','Marca ficticia'),('condiciones','Condición ficticia')]:self.result(self.admin,'/api/p2/catalog/save',{'kind':kind,'label':label})
        self.result(c,'/api/eventos',payload,expected=409)
        self.result(self.admin,'/api/p2/catalog/ready',{})
        self.result(c,'/api/eventos',payload)
        self.result(c,'/api/p2/template.xlsx?activity_id=revision',expected=403)
        self.result(c,'/api/dashboard?activity_id=revision',expected=403)
        self.result(self.admin,'/api/p2/assignment',{'user_id':first['id'],'activity_id':'revision','permissions':['carga_masiva','panel'],'reason':'Prueba de permisos'})
        status,raw,_=c.request('/api/p2/template.xlsx?activity_id=revision');self.assertEqual(status,200);self.assertTrue(raw.startswith(b'PK'))
        self.result(c,'/api/dashboard?activity_id=revision')

if __name__=='__main__':unittest.main()
