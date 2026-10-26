"""Prueba real del EXE compilado; únicamente loopback y datos ficticios temporales."""
import http.cookiejar
import json
from pathlib import Path
import queue
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

exe=Path(sys.argv[1]).resolve()
with tempfile.TemporaryDirectory(prefix='laboratorio-exe-ficticio-') as temp:
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    command=[str(exe),'--production','--data-dir',temp,'--port',str(port),'--no-browser']
    process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace')
    lines=queue.Queue()
    def read():
        for line in process.stdout:lines.put(line)
    threading.Thread(target=read,daemon=True).start()
    base=f'http://127.0.0.1:{port}';client=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    csrf='';key=None
    def request(path,data=None):
        payload=json.dumps(data).encode() if data is not None else None
        headers={'Content-Type':'application/json','X-CSRF-Token':csrf}
        try:response=client.open(urllib.request.Request(base+path,data=payload,headers=headers),timeout=15)
        except urllib.error.HTTPError as error:response=error
        with response:
            body=response.read()
            return response.status,json.loads(body) if 'application/json' in response.headers.get('Content-Type','') else body
    try:
        deadline=time.monotonic()+60
        while time.monotonic()<deadline:
            if process.poll() is not None:raise AssertionError('El ejecutable terminó antes de iniciar HTTP.')
            try:
                line=lines.get(timeout=.2)
                match=re.search(r'CLAVE TEMPORAL DE ADMIN .*?: (\S+)',line)
                if match:key=match.group(1)
                if key and request('/healthz')[0]==200:break
            except (queue.Empty,urllib.error.URLError,ConnectionError):pass
        assert key,'El primer inicio no produjo la clave temporal esperada.'
        assert request('/api/login',{'username':'admin','password':key})[0]==200
        status,me=request('/api/me');assert me['production_mode'] and me['user']['must_change'];csrf=me['csrf']
        assert request('/api/usuarios')[0]==403
        password='ClavePropiaFicticia2026!'
        assert request('/api/password',{'current_password':key,'password':password})[0]==200
        assert request('/api/login',{'username':'admin','password':password})[0]==200
        _,me=request('/api/me');csrf=me['csrf'];assert me['user']['must_complete_profile']
        assert request('/api/profile',{'full_name':'Maestro ficticio del EXE','identity_number':'00000000001','birth_date':'1990-01-01','phone':'0000000000','fleet':'','position':'Administración ficticia'})[0]==200
        assert request('/api/base/status')[0]==200
        assert me['delivered_phase']==2 and me['validated_phase']==1
        for kind,label in [('marcas','Marca ficticia'),('condiciones','Apto ficticio')]:
            assert request('/api/p2/catalog/save',{'kind':kind,'label':label})[0]==200
        assert request('/api/p2/article',{'code':'00010','valuation':'Nuevo','description':'Material ficticio'})[0]==200
        assert request('/api/p2/catalog/ready',{})[0]==200
        article=request('/api/p2/catalog')[1]['articles'][0]
        event={'activity_id':'sellado','work_date':'2026-10-24','operation_id':'exe-ficticio-1','data':{'serie':'00001','marca':'Marca ficticia','sap':'00010','clasificacion':'Nuevo','sap_config_id':article['id'],'color':'AZUL','sello_1':'000S1','sello_2':'000S2'}}
        assert request('/api/eventos',event)[0]==403
        preview=request('/api/p2/import/preview',{'activity_id':'sellado','rows':[event['data']|{'FECHA':'2026-10-26','USUARIO':'admin'}]})[1]
        assert not preview['errors'],preview
        assert request('/api/p2/import/confirm',{'preview_id':preview['preview_id']})[0]==200
        duplicate=request('/api/p2/import/preview',{'activity_id':'sellado','rows':[event['data']|{'FECHA':'2026-10-26','USUARIO':'admin'}]})[1]
        assert duplicate['errors'] and duplicate['errors'][0]['details'].get('seal_conflict')
        assert request('/api/p2/analysis?activity_id=sellado&desde=2026-10-26&hasta=2026-10-26')[1]['activities'][0]['quantity']==1
        for asset in ['app.js','app.css','table-tools.js','drilldown.js','profile-avatars.js','foundation-ui.js','foundation-ui.css','phase2-ui.js','labflows-ui.js','phase2.css','edesur.png']:
            assert request('/'+asset)[0]==200,asset
        assert request('/api/base/backup-now',{})[1]['status']=='incompleto'
        assert request('/api/auditoria/integridad')[1]['ok']
        print('EXE Windows: arranque, clave única, contraseña propia, perfil, RBAC, activos, respaldo y auditoría correctos; captura y bloqueo de sellos de fase 2 correctos.')
    finally:
        process.terminate();process.wait(timeout=15);process.stdout.close()
