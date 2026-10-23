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
        assert request('/api/eventos',{'activity_id':'revision'})[0]==423
        for asset in ['app.js','app.css','table-tools.js','drilldown.js','profile-avatars.js','foundation-ui.js','foundation-ui.css','edesur.png']:
            assert request('/'+asset)[0]==200,asset
        assert request('/api/base/backup-now',{})[1]['status']=='incompleto'
        assert request('/api/auditoria/integridad')[1]['ok']
        print('EXE Windows: arranque, clave única, contraseña propia, perfil, RBAC, activos, respaldo y auditoría correctos; operación bloqueada hasta validar fase 2.')
    finally:
        process.terminate();process.wait(timeout=15);process.stdout.close()
