"""Operación V34: transacciones locales, permisos por sesión y trazabilidad permanente."""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from collections import Counter
from contextlib import closing
import base64
import hashlib
import io
import json
import re
import secrets
import sqlite3
import uuid
import zipfile
from xml.sax.saxutils import escape
import production as p
import foundation as f
import documents as d

VALUATIONS = ['Nuevo', 'Recuperado-Reparado']
PERMISSIONS = {'ver','capturar','carga_masiva','proponer_baja','panel'}


def enabled(db):
    try:
        return f.setting(db, 'environment') == 'production' and f.setting(db, 'implemented_phase', 1) >= 2
    except sqlite3.OperationalError:
        return False


def init_schema(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS p2_receipt_providers(order_id INTEGER PRIMARY KEY REFERENCES receipt_orders(id),provider TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS p2_activity_preferences(activity_id TEXT PRIMARY KEY REFERENCES activities(id),illustration TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS p2_articles(id TEXT PRIMARY KEY,code TEXT NOT NULL,valuation TEXT NOT NULL,
      description TEXT NOT NULL,voltage TEXT NOT NULL DEFAULT '',active INTEGER NOT NULL DEFAULT 1,
      UNIQUE(code,valuation));
    CREATE TABLE IF NOT EXISTS p2_catalog(kind TEXT NOT NULL,label TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1,PRIMARY KEY(kind,label));
    CREATE TABLE IF NOT EXISTS p2_assignments(id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),
      activity_id TEXT NOT NULL REFERENCES activities(id),starts_at TEXT NOT NULL,ends_at TEXT,
      permissions_json TEXT NOT NULL,assigned_by INTEGER NOT NULL REFERENCES users(id),reason TEXT NOT NULL,
      target INTEGER,revoked_at TEXT,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS p2_meters(serial TEXT PRIMARY KEY,state TEXT NOT NULL DEFAULT 'activo',created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS p2_cycles(id INTEGER PRIMARY KEY,serial TEXT NOT NULL REFERENCES p2_meters(serial),
      number INTEGER NOT NULL,arrival_date TEXT NOT NULL,created_at TEXT NOT NULL,UNIQUE(serial,number));
    CREATE TABLE IF NOT EXISTS p2_event_details(event_id INTEGER PRIMARY KEY REFERENCES production_events(id),
      cycle_id INTEGER REFERENCES p2_cycles(id),duplicate_note TEXT NOT NULL DEFAULT '',delegation_reason TEXT NOT NULL DEFAULT '',assignment_id INTEGER REFERENCES p2_assignments(id));
    CREATE TABLE IF NOT EXISTS p2_seals(number TEXT NOT NULL,color TEXT NOT NULL,event_id INTEGER NOT NULL REFERENCES production_events(id),
      serial TEXT NOT NULL,cycle_id INTEGER REFERENCES p2_cycles(id),retired INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(number,color));
    CREATE TRIGGER IF NOT EXISTS p2_seals_no_delete BEFORE DELETE ON p2_seals BEGIN SELECT RAISE(ABORT,'No se borra un sello utilizado'); END;
    CREATE TRIGGER IF NOT EXISTS p2_seals_identity_immutable BEFORE UPDATE OF number,color,event_id,serial,cycle_id ON p2_seals BEGIN SELECT RAISE(ABORT,'La identidad de un sello utilizado es inmutable'); END;
    CREATE TABLE IF NOT EXISTS p2_scrap(id INTEGER PRIMARY KEY,serial TEXT NOT NULL REFERENCES p2_meters(serial),
      work_date TEXT NOT NULL,reason TEXT NOT NULL,notes TEXT NOT NULL,parts_json TEXT NOT NULL,
      status TEXT NOT NULL,proposed_by INTEGER NOT NULL REFERENCES users(id),assigned_by INTEGER REFERENCES users(id),
      resolved_by INTEGER REFERENCES users(id),resolution_reason TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,resolved_at TEXT);
    CREATE UNIQUE INDEX IF NOT EXISTS p2_one_pending_scrap ON p2_scrap(serial) WHERE status='pendiente';
    CREATE TABLE IF NOT EXISTS p2_jobs(id TEXT PRIMARY KEY,actor_id INTEGER NOT NULL REFERENCES users(id),
      kind TEXT NOT NULL,payload_json TEXT NOT NULL,expires_at TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'preparado',result_json TEXT);
    CREATE TABLE IF NOT EXISTS p2_profile_photos(user_id INTEGER PRIMARY KEY REFERENCES users(id),mime TEXT NOT NULL,content BLOB NOT NULL);
    ''')
    columns={row[1] for row in db.execute('PRAGMA table_info(p2_scrap)')}
    for name in ('operation_id','request_hash'):
        if name not in columns:db.execute(f'ALTER TABLE p2_scrap ADD COLUMN {name} TEXT')
    db.execute('CREATE UNIQUE INDEX IF NOT EXISTS p2_scrap_operation ON p2_scrap(operation_id)')


def install(app):
    with app.database() as db:
        init_schema(db)
        if enabled(db):return
    safety=app.create_backup()
    with app.database() as db, p._transaction(db):
        if enabled(db):
            return
        # Se versionan definiciones; nunca se reinterpretan los registros históricos.
        for row in db.execute('SELECT * FROM activities').fetchall():
            a=p._activity(db,row['id']);fields=a['fields']
            if a['id']=='recepcion':fields.append(p._field('proveedor','Proveedor',required=False,maximum=150))
            if a['id']=='sellado':
                fields=[field for field in fields if field['key'] not in {'sello_1','sello_2','color','tipo','movimiento'}]
                fields += [p._field('color','Color de los sellos','select',True,['AZUL','MORADO']),
                           p._field('sello_1','Sello #1',maximum=60),p._field('sello_2','Sello #2',maximum=60),
                           p._field('tipo','Tipo de sellado',required=False),p._field('movimiento','Movimiento',required=False)]
            keys={field['key'] for field in fields}
            if 'sap' in keys and 'clasificacion' not in keys:fields.append(p._field('clasificacion','Valoración','select',False,VALUATIONS))
            for field in fields:
                if field['key'] in {'condicion','condicion_visual'}:field.update(type='select',source='condiciones',options=[])
                if a['id']=='limpieza' and field['key']=='tiempo_minutos':field['required']=False
                if field['key']=='marca':field.update(type='select',source='marcas',options=[])
                if field['key']=='clasificacion':field['options']=VALUATIONS
            version=a['version']+1
            db.execute('INSERT INTO activity_versions VALUES(?,?,?,?,?,?,?)',(a['id'],version,a['name'],a['mode'],a['unit'],p._json(fields),p.now()))
            db.execute('UPDATE activities SET current_version=? WHERE id=?',(version,a['id']))
        # Una baja es una actividad asignable, pero su escritura se limita al flujo de autorización.
        if not db.execute("SELECT 1 FROM activities WHERE id='bajas'").fetchone():
            db.execute('INSERT INTO activities VALUES(?,?,?,?,?,?,?)',('bajas','Baja definitiva de medidores','individual','medidores',1,1,p.now()))
            fields=[p._field('serie','Serie'),p._field('motivo','Motivo'),p._field('piezas','Piezas aprovechadas',required=False),p._field('observaciones','Observaciones',required=False)]
            db.execute('INSERT INTO activity_versions VALUES(?,?,?,?,?,?,?)',('bajas',1,'Baja definitiva de medidores','individual','medidores',p._json(fields),p.now()))
        if not f.setting(db,'installation_id'):f.put_setting(db,'installation_id',uuid.uuid4().hex)
        f.put_setting(db,'validated_phase',1);f.put_setting(db,'implemented_phase',2)
        f.put_setting(db,'catalog_ready',False)
        p.audit(db,None,'instalacion','fase2','habilitar',after={'phase':2,'phase_one_validated':True,'safety_backup':str(safety)},reason='Continuación autorizada por el solicitante; historial y usuarios conservados')


def assignment(db, user_id, activity, permission='capturar'):
    now=p.now()
    for row in db.execute('SELECT * FROM p2_assignments WHERE user_id=? AND activity_id=? AND revoked_at IS NULL AND starts_at<=? AND (ends_at IS NULL OR ends_at>?) ORDER BY id DESC',(user_id,activity,now,now)):
        if permission in json.loads(row['permissions_json']):return dict(row)
    # Compatibilidad con accesos permanentes anteriores. Los nuevos temporales no se materializan aquí.
    if db.execute('SELECT 1 FROM user_activities WHERE user_id=? AND activity_id=? AND enabled=1',(user_id,activity)).fetchone() and permission!='proponer_baja':
        return {'id':None,'assigned_by':None}
    return None


def access(db,user,activity,permission='capturar'):
    if user['role'] in p.MANAGERS:return None
    if user['role']!='tecnico':raise p.ApiError('Este perfil no puede ejecutar la operación.',403)
    a=assignment(db,user['id'],activity,permission)
    if not a:raise p.ApiError('No tienes una asignación vigente con ese permiso para esta actividad.',403)
    return a


def valuation(value):
    key=p._fold(value).replace(' ','')
    if key=='nuevo':return 'Nuevo'
    if key in {'recuperado','reparado','recuperado/reparado','recuperado-reparado'}:return 'Recuperado-Reparado'
    raise p.ApiError('Selecciona la valoración Nuevo o Recuperado-Reparado.')


def save_article(db,user,data):
    f.administrator(user)
    code=p._text(data.get('code'),'Artículo SAP',60,True)
    if not isinstance(data.get('code'),str):raise p.ApiError('El código SAP debe ser texto.')
    val=valuation(data.get('valuation',data.get('classification')))
    before=db.execute('SELECT * FROM p2_articles WHERE code=? AND valuation=?',(code,val)).fetchone()
    aid=before['id'] if before else 'art_'+uuid.uuid4().hex
    description=p._text(data.get('description',data.get('label')),'Descripción SAP',500,True)
    voltage=p._text(data.get('voltage'),'Voltaje orientativo',100)
    active=data.get('active',True)
    if not isinstance(active,bool):raise p.ApiError('Estado del artículo inválido.')
    db.execute('INSERT INTO p2_articles VALUES(?,?,?,?,?,?) ON CONFLICT(code,valuation) DO UPDATE SET description=excluded.description,voltage=excluded.voltage,active=excluded.active',(aid,code,val,description,voltage,int(active)))
    if voltage:db.execute("INSERT OR IGNORE INTO catalog(kind,label) VALUES('voltajes',?)",(voltage,))
    # Mantiene la estructura de consulta existente para formularios y órdenes.
    db.execute('INSERT OR IGNORE INTO sap_catalog VALUES(?,?,?,?,?)',(code,voltage,val,1,p.now()))
    db.execute('INSERT INTO sap_configurations(id,code,voltage,classification,brand,model,label,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET voltage=excluded.voltage,classification=excluded.classification,label=excluded.label,active=excluded.active,updated_at=excluded.updated_at',(aid,code,voltage,val,'','',description,int(active),p.now(),p.now()))
    p.audit(db,user,'articulo',aid,'guardar',dict(before) if before else None,dict(db.execute('SELECT * FROM p2_articles WHERE id=?',(aid,)).fetchone()))
    return {'ok':True,'id':aid}


def prepare_sap(db,activity,raw,existing):
    raw=dict(raw)
    if existing and all(raw.get(key,'')==existing['data'].get(key,'') for key in ('sap','sap_config_id','clasificacion')):return raw
    code=raw.get('sap','')
    if not code:return raw
    if not isinstance(code,str):raise p.ApiError('El SAP debe conservarse como texto.')
    candidates=[dict(row) for row in db.execute('SELECT * FROM p2_articles WHERE code=? AND active=1',(code,))]
    if raw.get('sap_config_id'):candidates=[r for r in candidates if r['id']==raw['sap_config_id']]
    if raw.get('clasificacion'):candidates=[r for r in candidates if r['valuation']==valuation(raw['clasificacion'])]
    if len(candidates)!=1:raise p.ApiError('Selecciona un artículo SAP y su valoración vigentes. Un código puede tener ambas valoraciones.',409,needs_sap_configuration=True,configurations=candidates)
    item=candidates[0];raw['sap_config_id']=item['id'];raw['clasificacion']=item['valuation']
    # Marca, modelo y voltaje no se fuerzan a una única configuración.
    if not raw.get('voltaje') and item['voltage']:raw['voltaje']=item['voltage']
    return raw


def before_event(db,user,payload,normalized,existing=None,bulk=False):
    import labflows
    if labflows.enabled(db):labflows.guard(db,user,payload,normalized,bulk,existing)
    if normalized['activity_id']=='bajas':raise p.ApiError('Las bajas se registran desde el flujo de Baja definitiva.',403)
    access(db,user,normalized['activity_id'],'carga_masiva' if bulk else 'capturar')
    if not f.setting(db,'catalog_ready',False):raise p.ApiError('Administración debe cargar o confirmar el catálogo operativo antes de capturar.',409)
    if not existing and normalized['responsible_id']!=user['id']:
        p._manager(user);p._text(payload.get('delegation_reason'),'Motivo del registro delegado',1500,True)
    raw=normalized['data'];serial=raw.get('serie')
    if serial:
        meter=db.execute('SELECT state FROM p2_meters WHERE serial=?',(serial,)).fetchone()
        if meter and meter['state']=='baja':raise p.ApiError('La serie está dada de baja. Solo Administración puede revertir su baja.',409)
    if normalized['activity_id']=='recepcion' and raw.get('proveedor'):
        previous=db.execute('SELECT x.provider FROM receipt_orders o JOIN p2_receipt_providers x ON x.order_id=o.id WHERE o.order_number=? AND o.sap=?',(raw.get('numero_orden'),raw.get('sap'))).fetchone()
        if previous and previous['provider'] and previous['provider']!=raw['proveedor']:
            raise p.ApiError('El proveedor no coincide con la orden. Revisa el dato o corrige el proveedor desde Editar orden con motivo.',409)
    if existing and serial!=existing['data'].get('serie'):
        raise p.ApiError('La identidad de serie no se reasigna. Anula con motivo y crea el registro correcto.',409)
    if existing and existing['activity_id']=='sellado':
        if any(raw.get(k)!=existing['data'].get(k) for k in ('serie','sello_1','sello_2','color')):
            raise p.ApiError('Un sello utilizado no se reasigna. Anula con motivo y crea el registro correcto con sellos nuevos.',409)
    if normalized['activity_id']=='sellado':
        color=raw.get('color');numbers=[raw.get('sello_1'),raw.get('sello_2')]
        if not all(isinstance(n,str) and n.strip() for n in numbers):raise p.ApiError('Completa ambos sellos como texto, conservando sus ceros.')
        if numbers[0]==numbers[1]:raise p.ApiError('El Sello #1 y el Sello #2 deben ser diferentes.',409)
        for number in numbers:
            prior=db.execute('SELECT s.*,e.work_date,u.name responsible FROM p2_seals s JOIN production_events e ON e.id=s.event_id JOIN users u ON u.id=e.responsible_id WHERE s.number=? AND s.color=?',(number,color)).fetchone()
            if prior and (not existing or prior['event_id']!=existing['id']):
                raise p.ApiError('Sello ya utilizado: corrige el número/color o quita el registro. No se permite reutilizarlo.',409,seal_conflict={k:prior[k] for k in ('serial','work_date','responsible','number','color')})
    elif serial:
        params=[normalized['activity_id'],serial,normalized['work_date'],str(raw.get('condicion',raw.get('condicion_visual','')))]
        query="SELECT e.*,u.name responsible FROM production_events e JOIN users u ON u.id=e.responsible_id WHERE e.state='valido' AND e.activity_id=? AND json_extract(e.data_json,'$.serie')=? AND e.work_date=? AND COALESCE(json_extract(e.data_json,'$.condicion'),json_extract(e.data_json,'$.condicion_visual'),'')=?"
        if existing:query+=' AND e.id!=?';params.append(existing['id'])
        prior=db.execute(query+' ORDER BY e.id DESC LIMIT 1',params).fetchone()
        if prior and not str(payload.get('duplicate_note','')).strip():
            raise p.ApiError('Medidor repetido en la misma actividad, condición y fecha. Elige quitar o registrar con justificación.',409,needs_duplicate_note=True,previous={'id':prior['id'],'date':prior['work_date'],'time':prior['created_at'],'responsible':prior['responsible'],'condition':params[3]})


def after_event(db,user,payload,event):
    serial=event['data'].get('serie');cycle_id=None
    if serial:
        db.execute('INSERT OR IGNORE INTO p2_meters VALUES(?,?,?)',(serial,'activo',p.now()))
        cycle=db.execute('SELECT * FROM p2_cycles WHERE serial=? ORDER BY number DESC LIMIT 1',(serial,)).fetchone()
        # El cambio de fecha no implica otra llegada: una reparación puede durar
        # varios días. Volver a revisar/resellar después de un sellado previo
        # abre un ciclo nuevo; el operador también puede identificar otra llegada.
        sealed=bool(cycle and db.execute('SELECT 1 FROM p2_seals WHERE cycle_id=? LIMIT 1',(cycle['id'],)).fetchone())
        new_cycle=not cycle or payload.get('new_cycle') is True or sealed and event['activity_id'] in {'revision','sellado'}
        if new_cycle:
            number=cycle['number']+1 if cycle else 1
            cycle_id=db.execute('INSERT INTO p2_cycles(serial,number,arrival_date,created_at) VALUES(?,?,?,?)',(serial,number,event['work_date'],p.now())).lastrowid
        else:cycle_id=cycle['id']
    a=assignment(db,user['id'],event['activity_id'],'carga_masiva' if event.get('import_id') else 'capturar') if user['role']=='tecnico' else None
    db.execute('INSERT INTO p2_event_details VALUES(?,?,?,?,?)',(event['id'],cycle_id,p._text(payload.get('duplicate_note'),'Justificación',1500),p._text(payload.get('delegation_reason'),'Registro delegado',1500),a['id'] if a else None))
    if event['activity_id']=='recepcion' and event['data'].get('proveedor'):
        link=db.execute('SELECT order_id FROM receipt_links WHERE event_id=?',(event['id'],)).fetchone()
        if link:db.execute("INSERT INTO p2_receipt_providers VALUES(?,?) ON CONFLICT(order_id) DO UPDATE SET provider=CASE WHEN provider='' THEN excluded.provider ELSE provider END",(link['order_id'],event['data']['proveedor']))
    if event['activity_id']=='sellado':
        db.execute('UPDATE p2_seals SET retired=1 WHERE serial=?',(serial,))
        for number in (event['data']['sello_1'],event['data']['sello_2']):
            db.execute('INSERT INTO p2_seals VALUES(?,?,?,?,?,?)',(number,event['data']['color'],event['id'],serial,cycle_id,0))
    if payload.get('duplicate_note'):p.audit(db,user,'registro',event['id'],'repetido_justificado',after={'note':payload['duplicate_note']})


def personnel(db,user,uid=None):
    if uid is None:
        p._manager(user)
        rows=db.execute('SELECT * FROM users ORDER BY name,id').fetchall()
        if user['role']=='supervisor':rows=[r for r in rows if (r['access_role'] or r['role'])=='tecnico' or r['id']==user['id']]
        return {'people':[{'id':r['id'],'name':r['name'],'username':r['username'],'role':r['access_role'] or r['role'],'active':bool(r['active']),'position':f.profile(db,r['id'])['position'],'supervisor_id':f.supervisor_id(db,r['id'])} for r in rows]}
    row=db.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
    if not row:raise p.ApiError('No existe esa ficha.',404)
    role=row['access_role'] or row['role']
    if uid!=user['id'] and (user['role'] not in p.MANAGERS or user['role']=='supervisor' and role!='tecnico'):
        raise p.ApiError('No puedes consultar esta ficha.',403)
    profile=f.profile(db,uid);supervisor=f.supervisor_id(db,uid)
    person={'id':uid,'name':row['name'],'username':row['username'],'role':role,'active':bool(row['active']),'profile':profile,'supervisor_id':supervisor}
    if supervisor:
        s=db.execute('SELECT name FROM users WHERE id=?',(supervisor,)).fetchone();person['supervisor_name']=s['name'] if s else ''
    person['team']=[dict(r) for r in db.execute('SELECT u.id,u.name,u.username FROM user_supervisors s JOIN users u ON u.id=s.user_id WHERE s.supervisor_id=? ORDER BY u.name',(uid,))] if role in p.MANAGERS else []
    photo=db.execute('SELECT mime,content FROM p2_profile_photos WHERE user_id=?',(uid,)).fetchone()
    person['photo']=('data:'+photo['mime']+';base64,'+base64.b64encode(photo['content']).decode()) if photo else None
    return {'person':person}


def save_assignment(db,user,data):
    p._manager(user);uid=p._integer(data.get('user_id'),'Técnico')
    person=db.execute("SELECT * FROM users WHERE id=? AND active=1 AND COALESCE(access_role,role)='tecnico'",(uid,)).fetchone()
    if not person:raise p.ApiError('Selecciona un técnico activo.')
    activity=p._activity(db,p._text(data.get('activity_id'),'Actividad',80,True))
    import labflows
    if labflows.enabled(db) and activity['id'] in {'bajas','asignacion'}:raise p.ApiError('Actividad retirada de la operativa.',403)
    start=parse_instant(data.get('starts_at',p.now()));end=parse_instant(data['ends_at']) if data.get('ends_at') else None
    if end and end<=start:raise p.ApiError('El vencimiento debe ser posterior al inicio.')
    permissions=data.get('permissions',[])
    if not isinstance(permissions,list) or not permissions or any(not isinstance(x,str) or x not in PERMISSIONS for x in permissions):raise p.ApiError('Selecciona permisos válidos.')
    if activity['id']=='bajas' and any(x in permissions for x in ('capturar','carga_masiva')):raise p.ApiError('Para bajas de técnicos utiliza el permiso Proponer baja.')
    target=p._integer(data['target'],'Meta') if data.get('target') not in (None,'') else None
    aid=db.execute('INSERT INTO p2_assignments(user_id,activity_id,starts_at,ends_at,permissions_json,assigned_by,reason,target,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(uid,activity['id'],start,end,p._json(permissions),user['id'],p._text(data.get('reason'),'Motivo de asignación',1500,True),target,p.now())).lastrowid
    if target:
        db.execute('INSERT INTO production_goals(responsible_id,activity_id,target,start_date,end_date,unit,created_at,created_by) VALUES(?,?,?,?,?,?,?,?)',(uid,activity['id'],target,start[:10],end[:10] if end else start[:10],activity['unit'],p.now(),user['id']))
    p.audit(db,user,'asignacion',aid,'crear',after={'user_id':uid,'activity':activity['id'],'permissions':permissions,'starts_at':start,'ends_at':end,'target':target})
    return {'ok':True,'id':aid}


def parse_instant(value):
    try:
        instant=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        if instant.tzinfo is None:instant=instant.replace(tzinfo=f.ZONE)
        return instant.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    except (ValueError,TypeError):raise p.ApiError('Introduce una fecha y hora válida.') from None


def save_scrap(db,user,data):
    import labflows
    if labflows.enabled(db):raise p.ApiError('Bajas y piezas está deshabilitado por decisión del solicitante.',403)
    a=access(db,user,'bajas','proponer_baja')
    serial=p._text(data.get('serial'),'Serie',60,True)
    if not isinstance(data.get('serial'),str):raise p.ApiError('La serie debe ser texto.')
    work_date=p._date(data.get('work_date'));reason=p._text(data.get('reason'),'Motivo',1500,True)
    notes=p._text(data.get('notes'),'Observaciones',1500)
    parts=data.get('parts',[])
    if not isinstance(parts,list) or len(parts)>100:raise p.ApiError('Lista de piezas inválida.')
    cleaned=[];seen=set()
    for part in parts:
        name=p._text(part.get('name'),'Pieza',150,True)
        if name in seen or not db.execute("SELECT 1 FROM p2_catalog WHERE kind='piezas' AND label=? AND active=1",(name,)).fetchone():raise p.ApiError('Selecciona cada pieza una sola vez desde el catálogo.')
        seen.add(name);cleaned.append({'name':name,'quantity':p._integer(part.get('quantity'),'Cantidad de piezas')})
    operation_id=p._text(data.get('operation_id'),'Identificador de operación',160) or None
    request_hash=hashlib.sha256(p._json({'actor':user['id'],'serial':serial,'date':work_date,'reason':reason,'notes':notes,'parts':cleaned}).encode()).hexdigest()
    if operation_id:
        previous=db.execute('SELECT id,status,request_hash FROM p2_scrap WHERE operation_id=?',(operation_id,)).fetchone()
        if previous:
            if previous['request_hash']!=request_hash:raise p.ApiError('El identificador de baja ya se utilizó con otros datos.',409)
            return {'ok':True,'id':previous['id'],'status':previous['status'],'already_saved':True}
    db.execute('INSERT OR IGNORE INTO p2_meters VALUES(?,?,?)',(serial,'activo',p.now()))
    if db.execute('SELECT state FROM p2_meters WHERE serial=?',(serial,)).fetchone()['state']=='baja':raise p.ApiError('Este medidor ya está dado de baja.',409)
    if db.execute("SELECT 1 FROM p2_scrap WHERE serial=? AND status='pendiente'",(serial,)).fetchone():raise p.ApiError('Esta serie ya tiene una propuesta pendiente.',409)
    manager=user['role'] in p.MANAGERS
    sid=db.execute('INSERT INTO p2_scrap(serial,work_date,reason,notes,parts_json,status,proposed_by,assigned_by,resolved_by,created_at,resolved_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(serial,work_date,reason,notes,p._json(cleaned),'autorizada' if manager else 'pendiente',user['id'],a['assigned_by'] if a else user['id'],user['id'] if manager else None,p.now(),p.now() if manager else None)).lastrowid
    db.execute('UPDATE p2_scrap SET operation_id=?,request_hash=? WHERE id=?',(operation_id,request_hash,sid))
    if manager:db.execute("UPDATE p2_meters SET state='baja' WHERE serial=?",(serial,))
    p.audit(db,user,'baja',sid,'autorizar' if manager else 'proponer',after={'serial':serial,'parts':cleaned,'reason':reason})
    return {'ok':True,'id':sid,'status':'autorizada' if manager else 'pendiente'}


def resolve_scrap(db,user,data):
    import labflows
    if labflows.enabled(db):raise p.ApiError('Bajas y piezas está deshabilitado.',403)
    p._manager(user);ids=data.get('ids',[]);action=data.get('action')
    if not isinstance(ids,list) or not ids or len(ids)>5000 or len(set(map(str,ids)))!=len(ids):raise p.ApiError('Selecciona bajas diferentes.')
    if action not in {'autorizar','rechazar','revertir'}:raise p.ApiError('Acción de baja inválida.')
    reason=p._text(data.get('reason'),'Motivo de resolución',1500,action in {'rechazar','revertir'})
    if action=='revertir':f.administrator(user)
    for sid in ids:
        row=db.execute('SELECT * FROM p2_scrap WHERE id=?',(p._integer(sid,'Baja'),)).fetchone()
        if not row:raise p.ApiError('No existe la baja.',404)
        expected='autorizada' if action=='revertir' else 'pendiente'
        if row['status']!=expected:raise p.ApiError('La baja cambió de estado; actualiza la bandeja.',409)
        status={'autorizar':'autorizada','rechazar':'rechazada','revertir':'revertida'}[action]
        db.execute('UPDATE p2_scrap SET status=?,resolved_by=?,resolution_reason=?,resolved_at=? WHERE id=?',(status,user['id'],reason,p.now(),row['id']))
        if action in {'autorizar','revertir'}:db.execute('UPDATE p2_meters SET state=? WHERE serial=?',('baja' if action=='autorizar' else 'activo',row['serial']))
        p.audit(db,user,'baja',row['id'],action,before=dict(row),after={'status':status},reason=reason)
    return {'ok':True,'count':len(ids)}


def catalog(db):
    base={kind:[row[0] for row in db.execute('SELECT label FROM catalog WHERE kind=? AND active=1 ORDER BY label',(kind,))] for kind in ('marcas','voltajes','condiciones')}
    extra={kind:[row[0] for row in db.execute('SELECT label FROM p2_catalog WHERE kind=? AND active=1 ORDER BY label',(kind,))] for kind in ('modelos','piezas','puestos','tipos')}
    return {'catalog':{**base,**extra},'articles':[dict(row) for row in db.execute('SELECT * FROM p2_articles ORDER BY code,valuation')],'ready':f.setting(db,'catalog_ready',False)}


def catalog_save(db,user,data):
    f.administrator(user);kind=data.get('kind')
    if kind not in {'marcas','voltajes','condiciones','modelos','piezas','puestos','tipos'}:raise p.ApiError('Catálogo no válido.')
    label=p._text(data.get('label'),'Valor',150,True);old=p._text(data.get('old_label'),'Valor anterior',150)
    active=data.get('active',True)
    if not isinstance(active,bool):raise p.ApiError('Estado inválido.')
    table='catalog' if kind in {'marcas','voltajes','condiciones'} else 'p2_catalog'
    if old and old!=label:db.execute(f'UPDATE {table} SET active=0 WHERE kind=? AND label=?',(kind,old))
    db.execute(f'INSERT INTO {table}(kind,label,active) VALUES(?,?,?) ON CONFLICT(kind,label) DO UPDATE SET active=excluded.active',(kind,label,int(active)))
    p.audit(db,user,'catalogo',kind,'guardar',after={'label':label,'active':active,'previous':old})
    return {'ok':True}


def file_bytes(data):
    try:
        raw=base64.b64decode(data.get('content',''),validate=True)
    except (ValueError,TypeError):raise p.ApiError('Archivo codificado inválido.') from None
    if not raw or len(raw)>8*1024*1024:raise p.ApiError('Selecciona un archivo de hasta 8 MB.')
    return raw


def new_job(db,user,kind,payload):
    jid=uuid.uuid4().hex
    expires=(datetime.now(timezone.utc)+timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M:%SZ')
    db.execute('INSERT INTO p2_jobs(id,actor_id,kind,payload_json,expires_at) VALUES(?,?,?,?,?)',(jid,user['id'],kind,p._json(payload),expires))
    return jid


def job(db,user,jid,kind):
    row=db.execute('SELECT * FROM p2_jobs WHERE id=?',(jid,)).fetchone()
    if not row or row['actor_id']!=user['id'] or row['kind']!=kind or row['expires_at']<p.now():raise p.ApiError('La vista previa no existe, venció o pertenece a otra cuenta.',409)
    return row


def catalog_preview(db,user,data):
    f.administrator(user)
    matrix=d._read_xlsx(file_bytes(data),sheet_name='DATOS',raw_matrix=True)
    if not matrix or len(matrix[0])<9:raise p.ApiError('La hoja DATOS no tiene las columnas oficiales esperadas.')
    expected=['marca','tension','condicion','codigo','descripcion','valoracion']
    headers=[p._fold(str(matrix[0][i])) for i in (0,2,4,6,7,8)]
    if any(word not in actual for word,actual in zip(expected,headers)):raise p.ApiError('Verifica los encabezados MARCAS, TENSION, CONDICIÓN, CÓDIGO/ARTICULO/SAP, DESCRIPCIÓN y VALORACIÓN de DATOS.')
    result={'marcas':[],'voltajes':[],'condiciones':[],'articles':[]};seen=set()
    for number,line in enumerate(matrix[1:],2):
        line=list(line)+['']*9
        for kind,index in [('marcas',0),('voltajes',2),('condiciones',4)]:
            value=p._text(line[index],kind,150)
            if value and value not in result[kind]:result[kind].append(value)
        if line[6]:
            code=p._text(line[6],'SAP',60,True);val=valuation(line[8]);key=(code,val)
            if key in seen:raise p.ApiError(f'Fila {number}: el artículo SAP y valoración se repiten en DATOS.')
            seen.add(key);result['articles'].append({'code':code,'valuation':val,'description':p._text(line[7],'Descripción',500,True)})
    if not all(result[key] for key in ('marcas','voltajes','condiciones','articles')):raise p.ApiError('El catálogo oficial está incompleto.')
    return {'preview_id':new_job(db,user,'catalog',result),'counts':{key:len(value) for key,value in result.items()},'preview':result,'note':'Solo se procesa DATOS. No se importa PERSONAL ni producción histórica.'}


def catalog_confirm(db,user,data):
    f.administrator(user);row=job(db,user,data.get('preview_id'),'catalog')
    if row['status']=='confirmado':return {'ok':True,'already_saved':True}
    values=json.loads(row['payload_json'])
    for kind in ('marcas','voltajes','condiciones'):
        db.execute('UPDATE catalog SET active=0 WHERE kind=?',(kind,))
        for label in values[kind]:db.execute('INSERT INTO catalog(kind,label,active) VALUES(?,?,1) ON CONFLICT(kind,label) DO UPDATE SET active=1',(kind,label))
    db.execute('UPDATE p2_articles SET active=0');db.execute('UPDATE sap_configurations SET active=0')
    for article in values['articles']:save_article(db,user,article)
    import labflows
    if labflows.enabled(db):
        for label in ['Bueno','Condiciones óptimas','Dentro de lo establecido']:db.execute("INSERT INTO catalog(kind,label,active) VALUES('condiciones',?,1) ON CONFLICT(kind,label) DO UPDATE SET active=1",(label,))
    f.put_setting(db,'catalog_ready',True)
    db.execute("UPDATE p2_jobs SET status='confirmado' WHERE id=?",(row['id'],))
    p.audit(db,user,'catalogo','oficial','importar',after={key:len(value) for key,value in values.items()})
    return {'ok':True}


def columns(db,activity_id):
    import labflows
    if labflows.enabled(db) and activity_id in labflows.OFFICIAL:return labflows.OFFICIAL[activity_id]
    if activity_id=='bajas':return [('serie','SERIE'),('work_date','FECHA'),('motivo','MOTIVO'),('piezas','PIEZAS APROVECHADAS'),('observaciones','OBSERVACIONES')]
    a=p._activity(db,activity_id)
    cols=[('work_date','FECHA'),('responsible','NUMERO DE EMPLEADO')]
    if a['mode']!='individual':cols.append(('quantity','CANTIDAD'))
    if activity_id=='revision':
        basic=[('serie','MEDIDOR'),('marca','MARCA'),('voltaje','VOLTAJE'),('condicion','CONDICIÓN'),('observaciones','OBSERVACIONES')]
        return cols+basic+[(field['key'],field['label']) for field in a['fields'] if field['key'] not in {key for key,_ in basic}]+[('duplicate_note','JUSTIFICACION REPETIDO'),('delegation_reason','MOTIVO REGISTRO DELEGADO')]
    if activity_id=='sellado':
        ordered=[('serie','MEDIDOR'),('marca','MARCA'),('sap','ARTICULO (SAP)'),('clasificacion','VALORACIÓN'),('movimiento','MOVIMIENTO'),('responsible','USUARIO'),('work_date','FECHA'),('tipo','TIPO'),('color','COLOR'),('sello_1','SELLO #1'),('sello_2','SELLO #2')]
        return ordered+[(field['key'],field['label']) for field in a['fields'] if field['key'] not in {key for key,_ in ordered}]+[('delegation_reason','MOTIVO REGISTRO DELEGADO')]
    return cols+[(field['key'],field['label']) for field in a['fields']]+[('duplicate_note','JUSTIFICACION REPETIDO'),('delegation_reason','MOTIVO REGISTRO DELEGADO')]


def template(db,user,activity_id):
    access(db,user,activity_id,'carga_masiva' if activity_id!='bajas' else 'proponer_baja')
    cols=columns(db,activity_id);source=d.write_xlsx([label for _,label in cols],[['']*len(cols) for _ in range(500)],'Captura')
    ref=[];validations=[]
    a=p._activity(db,activity_id)
    fields={field['key']:field for field in a['fields']}
    for ci,(key,label) in enumerate(cols,1):
        choices=[]
        if key=='responsible':choices=[row[0] for row in db.execute("SELECT username FROM users WHERE active=1 AND COALESCE(access_role,role)!='visitante' ORDER BY username")] if user['role'] in p.MANAGERS else [user['username']]
        elif key=='sap':choices=[row[0] for row in db.execute('SELECT DISTINCT code FROM p2_articles WHERE active=1 ORDER BY code')]
        elif key=='piezas':choices=[row[0] for row in db.execute("SELECT label FROM p2_catalog WHERE kind='piezas' AND active=1 ORDER BY label")]
        elif key in fields and fields[key]['type']=='select':choices=fields[key].get('options',[])
        if choices:
            column=d._column(len(ref)+1);ref.append((label,choices))
            validations.append((d._column(ci),column,len(choices)))
    articles=[dict(row) for row in db.execute('SELECT * FROM p2_articles WHERE active=1 ORDER BY code,valuation')]
    for key,label in [('code','Artículo SAP vigente'),('description','Descripción SAP vigente'),('valuation','Valoración SAP vigente')]:ref.append((label,[article[key] for article in articles]))
    for kind,values in catalog(db)['catalog'].items():ref.append(('Catálogo '+kind,values))
    # Directorio con puestos en columnas adicionales de la guía.
    employees=[tuple(row) for row in db.execute("SELECT u.username,u.name,COALESCE(p.position,'') FROM users u LEFT JOIN employee_profiles p ON p.user_id=u.id WHERE u.active=1 AND COALESCE(u.access_role,u.role)!='visitante' ORDER BY u.username")] if user['role'] in p.MANAGERS else [(user['username'],user['name'],'')]
    for index,label in enumerate(('Código de empleado','Nombre','Puesto')):ref.append((label,[row[index] for row in employees]))
    guide=d.write_xlsx([label for label,_ in ref],[[values[i] if i<len(values) else '' for _,values in ref] for i in range(max((len(v) for _,v in ref),default=0))],'Guía de Referencia')
    out=io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(source)) as original,zipfile.ZipFile(io.BytesIO(guide)) as reference,zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as target:
        for name in original.namelist():
            value=original.read(name).decode('utf-8')
            if name=='xl/worksheets/sheet1.xml':
                dv=''.join(f'<dataValidation type="list" allowBlank="1" showErrorMessage="1" errorStyle="stop" errorTitle="Valor del catálogo" error="Selecciona un valor de la guía vigente" sqref="{col}2:{col}501"><formula1>Lista{rcol}</formula1></dataValidation>' for col,rcol,n in validations)
                value=value.replace('<pageMargins',f'<dataValidations count="{len(validations)}">{dv}</dataValidations><pageMargins')
            if name=='xl/workbook.xml':
                defined=''.join(f'<definedName name="Lista{rcol}">\'Guía de Referencia\'!${rcol}$2:${rcol}${n+1}</definedName>' for col,rcol,n in validations)
                value=value.replace('</sheets>','<sheet name="Guía de Referencia" sheetId="2" r:id="rId3"/></sheets><definedNames>'+defined+'</definedNames>')
            if name=='xl/_rels/workbook.xml.rels':value=value.replace('</Relationships>','<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/></Relationships>')
            if name=='[Content_Types].xml':value=value.replace('</Types>','<Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
            target.writestr(name,value.encode())
        target.writestr('xl/worksheets/sheet2.xml',reference.read('xl/worksheets/sheet1.xml'))
    raw=out.getvalue()
    import labflows
    return labflows.decorate_template(raw,activity_id) if labflows.enabled(db) and activity_id in labflows.OFFICIAL else raw


def row_payload(db,user,activity_id,row):
    normalized={d.normalize_header(k):v for k,v in row.items()}
    aliases={'numero_de_empleado':'responsible','sello_1':'sello_1','sello_2':'sello_2','articulo_sap':'sap','valoracion':'clasificacion','justificacion_repetido':'duplicate_note','motivo_registro_delegado':'delegation_reason','piezas_aprovechadas':'piezas'}
    for original,target in aliases.items():
        if original in normalized:normalized[target]=normalized[original]
    import labflows
    if labflows.enabled(db):normalized=labflows.adapt_row(db,user,activity_id,normalized)
    person=user['id']
    if normalized.get('responsible'):
        code=p._text(normalized['responsible'],'Código de empleado',60,True)
        target=db.execute('SELECT id FROM users WHERE username=? AND active=1',(code,)).fetchone()
        if not target:raise p.ApiError('Código de empleado no encontrado.')
        person=target['id']
        if user['role']=='tecnico' and person!=user['id']:raise p.ApiError('El técnico solo registra su propia producción.',403)
    if activity_id=='bajas':
        rawparts=normalized.get('piezas','');parts=[]
        if rawparts:
            # Nombre:Cantidad;Nombre:Cantidad. Una pieza sin cantidad equivale a una.
            for item in str(rawparts).split(';'):
                name,separator,amount=item.strip().rpartition(':')
                parts.append({'name':name.strip() if separator else item.strip(),'quantity':amount.strip() if separator else 1})
        return {'serial':normalized.get('serie',''),'work_date':normalized.get('work_date',''),'reason':normalized.get('motivo',''),'notes':normalized.get('observaciones',''),'parts':parts}
    a=p._activity(db,activity_id)
    return {'activity_id':activity_id,'work_date':normalized.get('work_date',''),'responsible_id':person,'quantity':normalized.get('quantity') or 1,'data':{field['key']:normalized.get(field['key'],'') for field in a['fields']},'duplicate_note':normalized.get('duplicate_note',''),'delegation_reason':normalized.get('delegation_reason',''),'operation_id':'carga_'+uuid.uuid4().hex}


def preview_rows(db,user,activity_id,rows):
    permission='proponer_baja' if activity_id=='bajas' else 'carga_masiva'
    access(db,user,activity_id,permission)
    if not isinstance(rows,list) or not 1<=len(rows)<=p.MAX_IMPORT_ROWS:raise p.ApiError('La carga debe contener entre 1 y 5000 filas.')
    results=[];errors=[];warnings=[];accepted=[]
    # Simulación transaccional: detecta también conflictos entre filas sin guardar
    # datos ni auditoría. Cada fila errónea vuelve a su savepoint.
    db.execute('SAVEPOINT vista_p2')
    try:
        for index,row in enumerate(rows,2):
            db.execute('SAVEPOINT fila_p2')
            try:
                if not isinstance(row,dict):raise p.ApiError('Fila inválida.')
                if row.get('_drop'):
                    results.append({'row':index,'state':'quitar','message':'Se omitirá con constancia en auditoría.'});db.execute('RELEASE fila_p2');continue
                payload=row_payload(db,user,activity_id,row)
                if activity_id=='bajas':saved=save_scrap(db,user,payload)
                else:saved=p._save_event(db,user,payload,import_id='p2_preview')
                accepted.append(row);results.append({'row':index,'state':'valida','serial':payload.get('serial',payload.get('data',{}).get('serie','')),'message':'Validada'})
                db.execute('RELEASE fila_p2')
            except (p.ApiError,sqlite3.IntegrityError) as error:
                db.execute('ROLLBACK TO fila_p2');db.execute('RELEASE fila_p2')
                details=getattr(error,'details',{})
                item={'row':index,'message':str(error),'details':details}
                errors.append(item);results.append({'row':index,'state':'error',**item})
                if details.get('needs_duplicate_note'):warnings.append(item)
    finally:
        db.execute('ROLLBACK TO vista_p2');db.execute('RELEASE vista_p2')
    jid=new_job(db,user,'rows',{'activity_id':activity_id,'rows':rows,'valid':not errors})
    return {'preview_id':jid,'rows':results,'rows_count':len(rows),'valid_count':len(accepted),'errors':errors,'warnings':warnings,'source_rows':rows}


def import_preview(db,user,data):
    activity=p._text(data.get('activity_id'),'Actividad',80,True)
    if 'rows' in data:rows=data['rows']
    else:
        import labflows
        rows=labflows.read_official(db,user,activity,data) if labflows.enabled(db) and activity in labflows.OFFICIAL else d.read_table(p._text(data.get('filename'),'Archivo',200,True),file_bytes(data),strict_text_ids=True)
    result=preview_rows(db,user,activity,rows)
    import labflows
    if labflows.enabled(db) and 'rows' not in data:
        source=hashlib.sha256(file_bytes(data)).hexdigest()
        previous=db.execute('SELECT job_id FROM lab_import_files WHERE activity_id=? AND sha256=?',(activity,source)).fetchone()
        if previous:raise p.ApiError('Este archivo ya fue importado. Consulta sus registros antes de volver a cargarlo.',409)
        token=job(db,user,result['preview_id'],'rows');saved=json.loads(token['payload_json']);saved['source_sha256']=source
        db.execute('UPDATE p2_jobs SET payload_json=? WHERE id=?',(p._json(saved),result['preview_id']))
    if 'rows' in data and data.get('previous_preview_id'):
        previous=job(db,user,data['previous_preview_id'],'rows');original=json.loads(previous['payload_json'])
        if original.get('source_sha256') and original['activity_id']==activity:
            current=job(db,user,result['preview_id'],'rows');payload=json.loads(current['payload_json']);payload['source_sha256']=original['source_sha256']
            db.execute('UPDATE p2_jobs SET payload_json=? WHERE id=?',(p._json(payload),result['preview_id']))
    return result


def import_confirm(db,user,data):
    row=job(db,user,data.get('preview_id'),'rows')
    if row['status']=='confirmado':return {'ok':True,**json.loads(row['result_json'])}
    payload=json.loads(row['payload_json'])
    if not payload['valid']:raise p.ApiError('Corrige o quita las filas con errores y vuelve a validar antes de guardar.',409)
    access(db,user,payload['activity_id'],'proponer_baja' if payload['activity_id']=='bajas' else 'carga_masiva')
    if payload.get('source_sha256'):
        previous=db.execute('SELECT job_id FROM lab_import_files WHERE activity_id=? AND sha256=?',(payload['activity_id'],payload['source_sha256'])).fetchone()
        if previous:raise p.ApiError('Este archivo ya fue importado desde otra vista previa. No se duplicó ningún registro.',409)
        db.execute('INSERT INTO lab_import_files VALUES(?,?,?)',(payload['activity_id'],payload['source_sha256'],row['id']))
    count=0;removed=0
    for index,raw in enumerate(payload['rows'],2):
        if raw.get('_drop'):
            removed+=1;p.audit(db,user,'importacion',row['id'],'quitar_error',after={'row':index,'serial':raw.get('serie',raw.get('MEDIDOR',''))},reason='El usuario seleccionó Es un error, quitar en la vista previa');continue
        record=row_payload(db,user,payload['activity_id'],raw)
        if payload['activity_id']=='bajas':
            record['operation_id']=f'p2scrap:{row["id"]}:{index}'
            save_scrap(db,user,record)
        else:
            record['operation_id']=f'p2import:{row["id"]}:{index}'
            p._save_event(db,user,record,import_id=row['id'])
        count+=1
    result={'imported':count,'removed':removed}
    db.execute("UPDATE p2_jobs SET status='confirmado',result_json=? WHERE id=?",(p._json(result),row['id']))
    p.audit(db,user,'importacion',row['id'],'confirmar',after=result)
    return {'ok':True,**result}


def sap_summary(db,user,query):
    if user['role'] not in p.MANAGERS:raise p.ApiError('Este resumen requiere supervisión o administración.',403)
    start=p._date(query['desde']) if query.get('desde') else '0001-01-01'
    end=p._date(query['hasta']) if query.get('hasta') else '9999-12-31'
    if start>end:raise p.ApiError('El rango de fechas está invertido.')
    booking=p._date(query.get('booking_date') or datetime.now(f.ZONE).date().isoformat())
    descriptions={(row['code'],row['valuation']):row['description'] for row in db.execute('SELECT * FROM p2_articles')}
    groups={}
    for row in db.execute("SELECT * FROM production_events WHERE state='valido' AND activity_id='sellado' AND work_date BETWEEN ? AND ? ORDER BY id",(start,end)):
        value=json.loads(row['data_json']);code=value.get('sap');val=value.get('clasificacion')
        key=(code,val)
        if key not in groups:groups[key]={'sap':code,'valuation':val,'description':descriptions.get(key,'Artículo histórico'),'warehouse':'3001' if val=='Nuevo' else '3007','movement':'501','quantity':0,'booking_date':booking,'records':[],'records_total':0,'records_are_preview':True}
        groups[key]['quantity']+=row['quantity'];groups[key]['records_total']+=1
        if len(groups[key]['records'])<200:groups[key]['records'].append({'id':row['id'],'serial':value.get('serie'),'date':row['work_date'],'responsible_id':row['responsible_id']})
    return {'title':'MEDIDORES RECUPERADOS CARGADOS A SAP','rows':list(groups.values()),'note':'Cantidades de registros válidos de sellado. Una serie puede aparecer en más de un ciclo. Selecciona una cantidad para comprobar sus registros.'}


def handle_get(db,user,path,query):
    if path=='/api/p2/analysis':
        import labflows
        if not labflows.enabled(db):raise p.ApiError('Actualiza la instalación.',423)
        return labflows.analysis(db,user,query)
    if path=='/api/p2/catalog':return catalog(db)
    if path=='/api/p2/personal':return personnel(db,user)
    match=re.fullmatch(r'/api/p2/personal/(\d+)',path)
    if match:return personnel(db,user,p._integer(match.group(1),'Ficha',1,2**63-1))
    if path=='/api/p2/assignments':
        where='' if user['role'] in p.MANAGERS else 'WHERE x.user_id=?'
        params=[] if not where else [user['id']]
        if user['role']=='visitante':raise p.ApiError('Perfil no autorizado.',403)
        rows=[dict(row) for row in db.execute(f'SELECT x.*,u.name technician,a.name activity,s.name assigned_by_name FROM p2_assignments x JOIN users u ON u.id=x.user_id JOIN activities a ON a.id=x.activity_id JOIN users s ON s.id=x.assigned_by {where} ORDER BY x.id DESC',params)]
        for row in rows:
            row['permissions']=json.loads(row.pop('permissions_json'));row['state']='Revocada' if row['revoked_at'] else 'Vencida' if row['ends_at'] and row['ends_at']<=p.now() else 'Programada' if row['starts_at']>p.now() else 'Vigente'
        return {'assignments':rows}
    if path=='/api/p2/scrap':
        if user['role'] not in p.MANAGERS and not any(assignment(db,user['id'],'bajas',permission) for permission in ('ver','panel','proponer_baja')):raise p.ApiError('No tienes acceso a Bajas.',403)
        where='' if user['role'] in p.MANAGERS else 'WHERE b.proposed_by=?'
        rows=[dict(row) for row in db.execute(f'SELECT b.*,u.name proposed_by_name,s.name resolved_by_name FROM p2_scrap b JOIN users u ON u.id=b.proposed_by LEFT JOIN users s ON s.id=b.resolved_by {where} ORDER BY b.id DESC',[user['id']] if where else [])]
        for row in rows:row['parts']=json.loads(row.pop('parts_json'))
        return {'scrap':rows,'summary':dict(Counter(row['status'] for row in rows))}
    if path=='/api/p2/meter':
        serial=p._text(query.get('serie'),'Serie',60,True)
        events=p._history(db,user,{'medidor':serial})
        meter=db.execute('SELECT * FROM p2_meters WHERE serial=?',(serial,)).fetchone()
        if user['role'] not in p.MANAGERS:
            # Sin revelar actividad ni identidad de otros técnicos.
            return {'meter':dict(meter) if meter else {'serial':serial,'state':'sin registro'},'history':events}
        return {'meter':dict(meter) if meter else {'serial':serial,'state':'sin registro'},'cycles':[dict(row) for row in db.execute('SELECT * FROM p2_cycles WHERE serial=? ORDER BY number',(serial,))],'seals':[dict(row) for row in db.execute('SELECT * FROM p2_seals WHERE serial=? ORDER BY event_id',(serial,))],'history':events}
    if path=='/api/p2/sap-summary':return sap_summary(db,user,query)
    return None


def handle_post(db,user,path,data,app=None):
    if not isinstance(data,dict):raise p.ApiError('Se esperaba un objeto de datos.')
    with p._transaction(db):
        if path=='/api/p2/people/preview':return people_preview(db,user,data,app)
        if path=='/api/p2/people/confirm':return people_confirm(db,user,data,app)
        if path=='/api/p2/catalog/save':return catalog_save(db,user,data)
        if path=='/api/p2/catalog/ready':
            f.administrator(user)
            if not all(catalog(db)['catalog'][kind] for kind in ('marcas','voltajes','condiciones')):raise p.ApiError('Completa marcas, voltajes y condiciones antes de confirmar.')
            f.put_setting(db,'catalog_ready',True);p.audit(db,user,'catalogo','manual','confirmar',reason='Administración confirma el catálogo operativo configurado');return {'ok':True}
        if path=='/api/p2/catalog/preview':return catalog_preview(db,user,data)
        if path=='/api/p2/catalog/confirm':return catalog_confirm(db,user,data)
        if path=='/api/p2/article':return save_article(db,user,data)
        if path=='/api/p2/assignment':return save_assignment(db,user,data)
        if path=='/api/p2/assignment/revoke':
            p._manager(user);reason=p._text(data.get('reason'),'Motivo',1500,True);aid=p._integer(data.get('id'),'Asignación');row=db.execute('SELECT * FROM p2_assignments WHERE id=?',(aid,)).fetchone()
            if not row:raise p.ApiError('No existe la asignación.',404)
            db.execute('UPDATE p2_assignments SET revoked_at=? WHERE id=?',(p.now(),aid));p.audit(db,user,'asignacion',aid,'revocar',before=dict(row),reason=reason);return {'ok':True}
        if path=='/api/p2/scrap':return save_scrap(db,user,data)
        if path=='/api/p2/scrap/resolve':return resolve_scrap(db,user,data)
        if path=='/api/p2/import/preview':return import_preview(db,user,data)
        if path=='/api/p2/import/confirm':return import_confirm(db,user,data)
        if path=='/api/p2/duplicate/discard':
            access(db,user,p._text(data.get('activity_id'),'Actividad',80,True))
            p.audit(db,user,'captura','descartada','quitar_error',after={'activity':data['activity_id'],'serial':p._text(data.get('serial'),'Serie',60)},reason='Es un error, quitar');return {'ok':True}
        if path=='/api/p2/photo':
            if user['role']=='visitante':raise p.ApiError('No autorizado.',403)
            raw=file_bytes(data)
            if len(raw)>300*1024:raise p.ApiError('La foto debe pesar hasta 300 KB.')
            mime='image/png' if raw.startswith(b'\x89PNG\r\n\x1a\n') else 'image/jpeg' if raw.startswith(b'\xff\xd8\xff') and raw.endswith(b'\xff\xd9') else None
            if not mime:raise p.ApiError('Selecciona una fotografía PNG o JPEG válida.')
            db.execute('INSERT INTO p2_profile_photos VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET mime=excluded.mime,content=excluded.content',(user['id'],mime,raw));p.audit(db,user,'perfil',user['id'],'foto',after={'bytes':len(raw),'mime':mime});return {'ok':True}
        if path=='/api/p2/photo/remove':
            db.execute('DELETE FROM p2_profile_photos WHERE user_id=?',(user['id'],));p.audit(db,user,'perfil',user['id'],'quitar_foto');return {'ok':True}
    raise p.ApiError('Acción de operación no encontrada.',404)


def people_preview(db,user,data,app):
    f.administrator(user)
    if app is None:raise p.ApiError('Falta el contexto de instalación.')
    matrix=d._read_xlsx(file_bytes(data),sheet_name='PERSONAL',raw_matrix=True)
    markers={p._fold(str(line[0])) for line in matrix if line}
    if not {'supervisores','tecnicos'}<=markers:raise p.ApiError('La hoja PERSONAL debe contener las secciones SUPERVISORES y TECNICOS con sus encabezados oficiales.')
    role=None;rows=[];codes=set();errors=[]
    for index,line in enumerate(matrix,1):
        values=list(line)+['']*5
        marker=p._fold(str(values[0]))
        if marker=='supervisores':role='supervisor';continue
        if marker=='tecnicos':role='tecnico';continue
        if not role or not values[1] or 'codigo' in p._fold(str(values[1])):continue
        try:
            code=app.validate_username(str(values[1]));name=app.validate_name(str(values[2]).strip()+' '+str(values[3]).strip());position=p._text(values[4],'Puesto',150,True)
            if code in codes:raise p.ApiError('Código de empleado duplicado en el archivo.')
            codes.add(code)
            existing=db.execute('SELECT id FROM users WHERE username=?',(code,)).fetchone()
            rows.append({'code':code,'name':name,'position':position,'role':role,'state':'existente; se conserva' if existing else 'nuevo'})
        except (ValueError,p.ApiError) as error:errors.append({'row':index,'message':str(error)})
    if not rows:raise p.ApiError('No se encontró el directorio en la hoja PERSONAL.')
    return {'preview_id':new_job(db,user,'people',{'rows':rows,'errors':errors}),'rows':rows,'errors':errors}


def people_confirm(db,user,data,app):
    f.administrator(user);row=job(db,user,data.get('preview_id'),'people')
    if row['status']=='confirmado':raise p.ApiError('Esta carga ya fue confirmada. Las claves temporales no se muestran de nuevo; utiliza Restablecer acceso si es necesario.',409)
    values=json.loads(row['payload_json'])
    if values['errors']:raise p.ApiError('Corrige los errores antes de importar.')
    credentials=[];preserved=0
    for person in values['rows']:
        if db.execute('SELECT 1 FROM users WHERE username=?',(person['code'],)).fetchone():preserved+=1;continue
        password=secrets.token_urlsafe(18)
        uid=app.insert_user(db,person['code'],person['name'],person['role'],password,1)
        db.execute('INSERT INTO employee_profiles(user_id,full_name,position) VALUES(?,?,?)',(uid,person['name'],person['position']))
        db.execute("INSERT OR IGNORE INTO p2_catalog(kind,label) VALUES('puestos',?)",(person['position'],))
        credentials.append({'username':person['code'],'name':person['name'],'temporary_password':password})
        p.audit(db,user,'users',uid,'importar_personal',after={'username':person['code'],'role':person['role']})
    db.execute("UPDATE p2_jobs SET status='confirmado' WHERE id=?",(row['id'],))
    return {'ok':True,'credentials':credentials,'preserved':preserved}
