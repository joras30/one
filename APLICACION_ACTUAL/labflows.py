"""Ajustes operativos solicitados: plantillas oficiales, captura ágil y análisis trazable."""
from collections import defaultdict,Counter
from datetime import date,timedelta,datetime
import io,zipfile,re,json
import xml.etree.ElementTree as ET
import production as p
import phase2 as q
import foundation as f
import documents as d

OFFICIAL={
 'revision':[('numero','#'),('work_date','FECHA'),('responsible','NUMERO DE EMPLEADO'),('serie','Medidor'),('marca','MARCA'),('sap','SAP'),('voltaje','VOLTAJE'),('condicion','CONDICIÓN'),('observaciones','OBSERVACIONES')],
 'sellado':[('serie','MEDIDOR'),('marca','MARCA'),('sap','ARTICULO'),('movimiento','MOVIMIENTO'),('responsible','USUARIO'),('work_date','FECHA'),('tipo','TIPO'),('color','COLOR'),('sello_1','SELLO #1'),('sello_2','SELLO #2')],
 'sap_carga':[('sap','Artuculos SAP'),('descripcion','Descripción de Materiales'),('almacen','Almacén'),('clase_movimiento','Clase de movimiento'),('quantity','Cantidad'),('fecha_contabilizacion','Fe.contabilización')]}
TITLES={'revision':'REGISTRO DIARIO/ REVISION TECNICA','sellado':'REGISTRO DIARIO MEDIDORES SELLADOS EN ALMACEN','sap_carga':'MEDIDORES RECUPERADOS CARGADOS EN SAP'}
def enabled(db):return q.enabled(db) and f.setting(db,'lab_revision',0)>=1

def install(app):
 with app.database() as db:
  if enabled(db):return
 safety=app.create_backup()
 with app.database() as db,p._transaction(db):
  if enabled(db):return
  db.execute('CREATE TABLE IF NOT EXISTS lab_import_files(activity_id TEXT NOT NULL,sha256 TEXT NOT NULL,job_id TEXT NOT NULL,PRIMARY KEY(activity_id,sha256))')
  for aid in ('revision','configuracion','limpieza','sellado'):
   a=p._activity(db,aid);fields=a['fields']
   if aid=='revision':
    wanted=['serie','marca','voltaje','condicion','resultado','observaciones','sap','sap_config_id','clasificacion']
    fields=[v for key in wanted for v in fields if v['key']==key]
   for field in fields:
    if field['key']=='sap':field['required']=True
    if field['key']=='resultado':field.update(label='Resultado de reutilización',required=False,options=['Reutilizable','No reutilizable','Pendiente'])
   name='MEDIDORES SELLADOS EN EL LABORATORIO' if aid=='sellado' else a['name']
   version=a['version']+1
   db.execute('INSERT INTO activity_versions VALUES(?,?,?,?,?,?,?)',(aid,version,name,a['mode'],a['unit'],p._json(fields),p.now()))
   db.execute('UPDATE activities SET name=?,current_version=? WHERE id=?',(name,version,aid))
  db.execute("UPDATE activities SET active=0 WHERE id IN ('asignacion','bajas')")
  for label in ['Bueno','Condiciones óptimas','Dentro de lo establecido']:db.execute("INSERT OR IGNORE INTO catalog(kind,label) VALUES('condiciones',?)",(label,))
  if not db.execute("SELECT 1 FROM activities WHERE id='sap_carga'").fetchone():
   fields=[p._field('sap','Artículo SAP'),p._field('descripcion','Descripción de Materiales'),p._field('almacen','Almacén','select',True,['3001','3007']),p._field('clase_movimiento','Clase de movimiento'),p._field('fecha_contabilizacion','Fecha de contabilización','date'),p._field('clasificacion','Valoración','select',False,q.VALUATIONS),p._field('sap_config_id','Artículo',required=False)]
   db.execute('INSERT INTO activities VALUES(?,?,?,?,?,?,?)',('sap_carga',TITLES['sap_carga'],'lote','medidores',1,1,p.now()))
   db.execute('INSERT INTO activity_versions VALUES(?,?,?,?,?,?,?)',('sap_carga',1,TITLES['sap_carga'],'lote','medidores',p._json(fields),p.now()))
  f.put_setting(db,'lab_revision',1)
  p.audit(db,None,'instalacion','lab-r1','ajustar',after={'backup':str(safety),'retiradas':['asignacion','bajas']},reason='Ajustes del solicitante del 26 de octubre: rapidez, planillas oficiales y paneles propios')

def guard(db,user,payload,normalized,bulk=False,existing=None):
 aid=normalized['activity_id']
 if aid in {'asignacion','bajas'}:raise p.ApiError('Actividad retirada de la operativa.',403)
 if aid in {'sellado','sap_carga'} and not bulk and not existing:raise p.ApiError('Esta actividad se registra desde su carga masiva oficial.',403)
 if aid=='sap_carga':
  v=normalized['data']
  if v.get('clase_movimiento')!='501':raise p.ApiError('La clase de movimiento de esta planilla debe ser 501.')
  expected='Nuevo' if v.get('almacen')=='3001' else 'Recuperado-Reparado'
  if v.get('clasificacion')!=expected:raise p.ApiError('El almacén no coincide con la valoración.')

def adapt_row(db,user,aid,normalized,context=None):
 n=dict(normalized);ctx=context or {}
 for src,dst in {'articulo':'sap','artuculos_sap':'sap','articulos_sap':'sap','descripcion_de_materiales':'descripcion','fe_contabilizacion':'fecha_contabilizacion','clase_de_movimiento':'clase_movimiento'}.items():
  if src in n:n[dst]=n[src]
 for key in ('responsible','resultado','clasificacion','delegation_reason'):
  if not n.get(key) and ctx.get(key):n[key]=ctx[key]
 if aid=='sap_carga':
  n['responsible']=user['username'];n['delegation_reason']=''
  n['fecha_contabilizacion']=d._date_value(n.get('fecha_contabilizacion',''));n['work_date']=n['fecha_contabilizacion'];n['clasificacion']='Nuevo' if n.get('almacen')=='3001' else 'Recuperado-Reparado'
 if aid=='sellado' and not n.get('clasificacion'):
  try:n['clasificacion']=q.valuation(n.get('tipo',''))
  except p.ApiError:pass
 if n.get('sap') and not n.get('clasificacion'):
  vals=[row[0] for row in db.execute('SELECT valuation FROM p2_articles WHERE active=1 AND code=?',(n['sap'],))]
  if len(vals)==1:n['clasificacion']=vals[0]
 if n.get('responsible') and str(n['responsible'])!=user['username'] and not n.get('delegation_reason'):n['delegation_reason']='Carga de planilla oficial; producción atribuida por código de empleado de la fila.'
 return n

def read_official(db,user,aid,data):
 raw=q.file_bytes(data);name=data.get('filename','')
 if name.lower().endswith('.xlsx'):
  matrix=d._read_xlsx(raw,raw_matrix=True,strict_text_ids=True)
  rows=None;expected=[d.normalize_header(v) for _,v in OFFICIAL[aid]]
  for pos,row in enumerate(matrix[:12]):
   trim=list(row)
   while trim and not str(trim[-1]).strip():trim.pop()
   if [d.normalize_header(v) for v in trim]==expected:
    rows=d._records(matrix[pos:]);break
  if rows is None:raise p.ApiError('La planilla debe conservar exactamente las columnas del modelo oficial: '+', '.join(v for _,v in OFFICIAL[aid]))
 else:
  rows=d.read_table(name,raw,strict_text_ids=True)
  if rows and list(rows[0])!=[d.normalize_header(v) for _,v in OFFICIAL[aid]]:raise p.ApiError('Usa las columnas y el orden de la plantilla oficial descargable.')
 context=data.get('context',{})
 if not isinstance(context,dict):raise p.ApiError('Parámetros de carga inválidos.')
 result=[]
 for row in rows:
  n=adapt_row(db,user,aid,{d.normalize_header(k):v for k,v in row.items()},context)
  if aid=='sap_carga':n['responsible']=user['username'];n['delegation_reason']=''
  result.append(n)
 return result

def decorate_template(raw,aid):
 """Mantiene desplegables, agrega título y estilo del modelo sin columnas extra."""
 NS='http://schemas.openxmlformats.org/spreadsheetml/2006/main';ET.register_namespace('',NS)
 def tag(n):return '{'+NS+'}'+n
 out=io.BytesIO()
 with zipfile.ZipFile(io.BytesIO(raw)) as src,zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as dst:
  for name in src.namelist():
   data=src.read(name)
   if name=='xl/worksheets/sheet1.xml':
    root=ET.fromstring(data);sd=root.find(tag('sheetData'))
    for row in sd:
     row.set('r',str(int(row.get('r'))+2))
     for cell in row:cell.set('r',re.sub(r'\d+$',str(int(re.search(r'\d+$',cell.get('r'))[0])+2),cell.get('r')))
    row=ET.Element(tag('row'),r='1',ht='25',customHeight='1');cell=ET.SubElement(row,tag('c'),r='A1',t='inlineStr',s='1');ET.SubElement(ET.SubElement(cell,tag('is')),tag('t')).text=TITLES[aid];sd.insert(0,row)
    for el in root.iter():
     if el.get('sqref'):el.set('sqref',re.sub(r'([A-Z]+)(\d+)',lambda m:m[1]+str(int(m[2])+2),el.get('sqref')))
    for element in root.iter():
     if element.tag==tag('autoFilter') and element.get('ref'):element.set('ref',re.sub(r'([A-Z]+)(\d+)',lambda m:m[1]+str(int(m[2])+2),element.get('ref')))
     if element.tag==tag('pane'):
      if element.get('ySplit'):element.set('ySplit',str(int(element.get('ySplit'))+2))
      if element.get('topLeftCell'):element.set('topLeftCell',re.sub(r'([A-Z]+)(\d+)',lambda m:m[1]+str(int(m[2])+2),element.get('topLeftCell')))
    dim=root.find(tag('dimension'))
    if dim is not None:dim.set('ref',f'A1:{d._column(len(OFFICIAL[aid]))}503')
    merged=ET.Element(tag('mergeCells'),count='1');ET.SubElement(merged,tag('mergeCell'),ref='A1:'+d._column(len(OFFICIAL[aid]))+'1')
    idx=list(root).index(root.find(tag('dataValidations'))) if root.find(tag('dataValidations')) is not None else len(root)-1;root.insert(idx,merged)
    data=ET.tostring(root,encoding='utf-8',xml_declaration=True)
   dst.writestr(name,data)
 return out.getvalue()

def analysis(db,user,query):
 if user['role']=='visitante':raise p.ApiError('Acceso no autorizado.',403)
 start=p._date(query.get('desde') or datetime.now(f.ZONE).date().replace(day=1).isoformat());end=p._date(query.get('hasta') or datetime.now(f.ZONE).date().isoformat())
 if start>end:raise p.ApiError('El inicio no puede ser posterior al final.')
 if (date.fromisoformat(end)-date.fromisoformat(start)).days>730:raise p.ApiError('Elige hasta dos años por consulta.')
 activity=query.get('activity_id','');params=[start,end];where="e.state='valido' AND e.work_date BETWEEN ? AND ? AND e.activity_id NOT IN ('asignacion','bajas')"
 if activity:where+=' AND e.activity_id=?';params.append(activity)
 if user['role'] not in p.MANAGERS:where+=' AND e.responsible_id=?';params.append(user['id'])
 rows=db.execute('SELECT e.*,u.name technician,u.username code,a.name activity_name FROM production_events e JOIN users u ON u.id=e.responsible_id JOIN activities a ON a.id=e.activity_id WHERE '+where+' ORDER BY e.work_date,e.id',params).fetchall()
 grouped={};daily={};monthly={};tech={};sap={};outcomes=Counter();movements=[];persondays=defaultdict(Counter)
 for row in rows:
  v=json.loads(row['data_json']);aid=row['activity_id'];unit=row['unit'];qty=row['quantity']
  key=aid
  if aid=='sap_carga':movements.append({**v,'quantity':qty,'imported_by':row['recorded_by']})
  else:persondays[(aid,row['responsible_id'])][row['work_date']]+=qty
  if key not in grouped:grouped[key]={'activity_id':aid,'label':row['activity_name'],'unit':unit,'quantity':0,'events':0,'series':set()}
  grouped[key]['quantity']+=qty;grouped[key]['events']+=1
  if v.get('serie'):grouped[key]['series'].add(v['serie'])
  for store,key in [(daily,(aid,row['work_date'])),(monthly,(aid,row['work_date'][:7],row['responsible_id'])),(tech,(aid,row['responsible_id'])),(sap,(aid,v.get('sap',''),v.get('clasificacion',''),v.get('almacen','')))]:
   if aid=='sap_carga' and store is tech:continue
   if aid=='sap_carga' and store is monthly:continue
   if key not in store:store[key]={'activity_id':aid,'activity':row['activity_name'],'unit':unit,'quantity':0,'technician':row['technician'],'code':row['code'],'responsible_id':row['responsible_id']}
   store[key]['quantity']+=qty
  if aid=='revision':outcomes[p._fold(v.get('resultado',''))]+=1
 prev_end=date.fromisoformat(start)-timedelta(days=1);prev_start=prev_end-(date.fromisoformat(end)-date.fromisoformat(start))
 previous={row[0]:row[1] for row in db.execute('SELECT e.activity_id,SUM(e.quantity) FROM production_events e WHERE '+where+' GROUP BY e.activity_id',[prev_start.isoformat(),prev_end.isoformat(),*params[2:]])}
 activities=[]
 for v in grouped.values():
  v['unique_series']=len(v.pop('series'));v['previous']=previous.get(v['activity_id'],0);v['variation']=v['quantity']-v['previous'];v['growth_pct']=v['variation']/v['previous']*100 if v['previous'] else None;activities.append(v)
 days=[]
 for (aid,day),v in daily.items():days.append({**v,'date':day})
 months=[{**v,'month':month} for (aid,month,person),v in monthly.items()]
 ranking=sorted(tech.values(),key=lambda v:(v['activity_id'],-v['quantity'],v['code']))
 for aid in grouped:
  group=[v for v in ranking if v['activity_id']==aid];last=None;rank=0
  for idx,v in enumerate(group,1):
   if v['quantity']!=last:rank=idx;last=v['quantity']
   v['rank']=rank
 span=(date.fromisoformat(end)-date.fromisoformat(start)).days
 dayslist=[(date.fromisoformat(start)+timedelta(days=n)).isoformat() for n in range(span+1)] if span<31 else [];matrix=[]
 for v in ranking:
  counts=persondays[(v['activity_id'],v['responsible_id'])]
  effective=sum(n>0 for n in counts.values());matrix.append({**v,'days':dict(counts),'effective_days':effective,'average':v['quantity']/effective if effective else None})
 approved=outcomes['reutilizable']+outcomes['apto'];rejected=outcomes['no reutilizable']+outcomes['no apto'];evaluated=approved+rejected
 return {'from':start,'to':end,'movements':movements,'matrix_available':span<31,'previous_from':prev_start.isoformat(),'previous_to':prev_end.isoformat(),'activity_id':activity,'events':len(rows),'activities':activities,'daily':days,'monthly':months,'ranking':ranking,'dates':dayslist,'matrix':matrix,'sap':[{**v,'sap':code,'valuation':val,'warehouse':warehouse} for (aid,code,val,warehouse),v in sap.items()],'quality':{'approved':approved,'rejected':rejected,'pending':sum(outcomes.values())-evaluated,'evaluated':evaluated,'approval_pct':approved/evaluated*100 if evaluated else None},'note':'Unidades separadas por actividad. SAP registra movimientos importados: no se mezcla ni se vuelve a contar como sellado. Promedio individual: días con producción efectiva; la asistencia aún no está integrada.'}

def report(data,kind):
 if kind=='sap':
  return [label for _,label in OFFICIAL['sap_carga']],[[v.get(key,'') for key,_ in OFFICIAL['sap_carga']] for v in data['movements']],TITLES['sap_carga']
 if kind=='daily':
  if not data['matrix_available']:raise p.ApiError('El reporte diario en columnas admite hasta 31 días; reduce el rango o usa Mensual.')
  headers=['Actividad','Unidad','Código','Técnico',*data['dates'],'Total','Días efectivos','Promedio individual']
  rows=[[v['activity'],v['unit'],v['code'],v['technician'],*[v['days'].get(day,0) for day in data['dates']],v['quantity'],v['effective_days'],round(v['average'],2) if v['average'] is not None else 'Sin base'] for v in data['matrix']]
  for activity in data['activities']:
   totals=[sum(v['days'].get(day,0) for v in data['matrix'] if v['activity_id']==activity['activity_id']) for day in data['dates']]
   rows.append([activity['label'],activity['unit'],'','TOTAL GENERAL',*totals,activity['quantity'],'',''])
 elif kind=='monthly':headers=['Actividad','Unidad','Mes','Código','Técnico','Cantidad'];rows=[[v['activity'],v['unit'],v['month'],v['code'],v['technician'],v['quantity']] for v in data['monthly']]
 else:headers=['Actividad','Unidad','Puesto','Código','Técnico','Cantidad'];rows=[[v['activity'],v['unit'],v['rank'],v['code'],v['technician'],v['quantity']] for v in data['ranking']]
 if kind!='daily':
  for activity in data['activities']:
   if activity['activity_id']!='sap_carga':rows.append([activity['label'],activity['unit'],'','','TOTAL GENERAL',activity['quantity']])
 return headers,rows,'Producción del laboratorio · '+data['from']+' a '+data['to']
