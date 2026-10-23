'use strict';

const $ = (id) => document.getElementById(id);
const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = (value) => new Intl.NumberFormat('es-DO', {maximumFractionDigits: 2}).format(Number(value) || 0);
const today = () => new Intl.DateTimeFormat('en-CA', {timeZone: 'America/Santo_Domingo',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
const prettyDate = (value) => value ? new Intl.DateTimeFormat('es-DO',{dateStyle:'medium',timeZone:'America/Santo_Domingo'}).format(new Date(String(value).length === 10 ? `${value}T12:00:00-04:00` : value)) : '—';
const prettyTime = (value) => value ? new Intl.DateTimeFormat('es-DO',{dateStyle:'short',timeStyle:'short',timeZone:'America/Santo_Domingo'}).format(new Date(value)) : '—';
const newOperation = () => window.crypto?.randomUUID ? crypto.randomUUID() : `op-${Date.now()}-${Math.random().toString(36).slice(2)}`;
const roleNames = {tecnico:'Colaborador',supervisor:'Supervisor',administrador:'Administrador',visitante:'Visitante'};
const modeNames = {lote:'Por cantidad',individual:'Por medidor',recepcion:'Recepción parcial'};
const S = {user:null,csrf:'',demo:false,publicDemo:false,setup:false,view:'dashboard',activities:[],users:[],catalog:{marcas:[],voltajes:[],condiciones:[]},sap:[],page:1,pages:1,records:[],preview:null,operation:newOperation(),charts:{},navigation:0};
const isManager = () => ['supervisor','administrador'].includes(S.user?.role);
const isVisitor = () => S.user?.role === 'visitante';
const activeActivities = () => S.activities.filter((a) => a.active && (isManager() || a.assigned !== false));
const personOptions = () => S.users.filter((u) => u.active && u.role !== 'visitante');
const labels = {serie:'Serie',sap:'Código SAP',marca:'Marca',modelo:'Modelo',sap_config_id:'Configuración SAP',tipo_inspeccion:'Tipo de inspección',fallo:'Fallo detectado',valor_referencia:'Valor de referencia',valor_medido:'Valor medido',tolerancia_pct:'Tolerancia (%)',desviacion_pct:'Desviación (%)',fuera_tolerancia:'Fuera de tolerancia',voltaje:'Voltaje',condicion:'Condición técnica',clasificacion:'Nuevo / recuperado',resultado:'Resultado de revisión',tiempo_minutos:'Tiempo del lote (min)',condicion_visual:'Condición visual',tipo_configuracion:'Tipo de configuración',destino:'Destinatario / destino',tipo_articulo:'Tipo de artículo',numero_orden:'Número de orden',proceso:'Proceso de recepción',cantidad_esperada:'Cantidad esperada',observaciones:'Observaciones',work_date:'Fecha de trabajo',responsible_id:'Responsable',quantity:'Cantidad',state:'Estado',name:'Nombre',active:'Activo',role:'Perfil',activity_ids:'Actividades asignadas'};
const pages = {
  dashboard:['PANORAMA GENERAL','Resumen de producción','Una vista clara del trabajo y los resultados del laboratorio.'],
  quality:['CONTROL DE CALIDAD','Inspección y calibración','Resultados técnicos, fallos y desviaciones con criterios visibles.'],
  comparison:['ANALÍTICA','Comparar períodos','Mide la variación entre períodos conservando cada actividad y unidad.'],
  capture:['OPERACIÓN DIARIA','Registrar actividad','Captura lo realizado; cada actividad pide sus propios datos.'],
  records:['PRODUCCIÓN','Registros del laboratorio','Consulta, filtra y descarga el detalle de la actividad.'],
  history:['TRAZABILIDAD','Consultar medidor','Cada revisión conserva su fecha, resultado y responsable.'],
  activities:['CONFIGURACIÓN','Actividades del laboratorio','Formularios que evolucionan conservando lo registrado.'],
  import:['CARGA SUPERVISADA','Importar Excel o CSV','Revisa la información antes de incorporarla a la producción.'],
  receipts:['SEGUIMIENTO','Recepciones y pendientes','Cada entrega suma al lote y conserva su detalle.'],
  goals:['PLANIFICACIÓN','Metas de producción','Objetivos claros por colaborador, actividad y período.'],
  users:['EQUIPO','Colaboradores y accesos','Personas, actividades habilitadas y acceso sencillo.'],
  catalogs:['CATÁLOGOS','SAP, marcas y condiciones','Listas actualizables para mantener una captura consistente.'],
  audit:['CONTROL','Historial de cambios','Correcciones y anulaciones con su motivo y responsable.'],
  account:['MI CUENTA','Perfil y contraseña','Gestiona tu acceso al sistema.']
};

class ApiError extends Error { constructor(message, status, payload) { super(message); this.status = status; this.payload = payload; } }
async function api(path, payload) {
  const headers = {'Accept':'application/json'};
  if (payload !== undefined) { headers['Content-Type']='application/json'; if (S.csrf) headers['X-CSRF-Token']=S.csrf; }
  let response;
  try { response = await fetch(path, {method:payload === undefined ? 'GET':'POST',headers,credentials:'same-origin',body:payload === undefined ? undefined:JSON.stringify(payload)}); }
  catch (_) { throw new ApiError('No se pudo conectar. Comprueba que la aplicación siga abierta.',0,{}); }
  let data;
  try { data = await response.json(); } catch (_) { throw new ApiError('La aplicación devolvió una respuesta inesperada. Intenta de nuevo.',response.status,{}); }
  if (!response.ok) {
    if (response.status === 401 && S.user && !path.endsWith('/password')) { S.user=null; S.csrf=''; showAuth(false); }
    throw new ApiError(data.error || 'No se pudo completar la operación.',response.status,data);
  }
  return data;
}
function toast(message, kind='success') {
  const node=document.createElement('div'); node.className=`toast ${kind}`; node.setAttribute('role',kind==='error'?'alert':'status'); node.textContent=message;
  $('toast-container').append(node); setTimeout(()=>node.remove(),6500);
}
function showError(node, error) { node.textContent=error.message || String(error); node.classList.remove('hidden'); }
function clearError(node) { node.textContent=''; node.classList.add('hidden'); }
async function busy(button, action, errorNode) {
  const before=button?.innerHTML;
  if(button) { button.disabled=true; button.setAttribute('aria-busy','true'); }
  if(errorNode) clearError(errorNode);
  try { return await action(); } catch(error) { if(errorNode) showError(errorNode,error); else toast(error.message,'error'); return undefined; }
  finally { if(button) { button.disabled=false; button.removeAttribute('aria-busy'); if(before!==undefined) button.innerHTML=before; } }
}
function empty(message, title='Sin registros todavía') { return `<div class="empty-state"><span class="empty-icon" aria-hidden="true">▤</span><h3>${escapeHtml(title)}</h3><p>${escapeHtml(message)}</p></div>`; }
function badge(text, kind='soft') { return `<span class="badge ${kind}">${escapeHtml(text)}</span>`; }
function table(headers, rows, emptyMessage='No hay información para esta selección.') {
  if(!rows.length) return empty(emptyMessage,'Sin resultados');
  return `<div class="table-wrap" tabindex="0" aria-label="Tabla de datos desplazable"><table class="data-table"><thead><tr>${headers.map((h)=>`<th scope="col">${escapeHtml(h)}</th>`).join('')}</tr></thead><tbody>${rows.map((r)=>`<tr>${r.map((c)=>`<td>${c}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
}
function options(items, current='', first='Selecciona una opción') {
  return (first === null ? '' : `<option value="">${escapeHtml(first)}</option>`) + items.map((item)=>{ const value=typeof item==='object'?item.value:item; const label=typeof item==='object'?item.label:item; return `<option value="${escapeHtml(value)}"${String(value)===String(current)?' selected':''}>${escapeHtml(label)}</option>`; }).join('');
}
function setRoleVisibility() {
  document.querySelectorAll('.manager-only').forEach((n)=>n.classList.toggle('hidden',!isManager()));
  document.querySelectorAll('.writer-only,.detail-only').forEach((n)=>n.classList.toggle('hidden',isVisitor()));
  document.querySelectorAll('.administrator-only').forEach((n)=>n.classList.toggle('hidden',S.user?.role!=='administrador'));
}
function setMenu(open) { document.body.classList.toggle('menu-open',open); $('sidebar-backdrop').classList.toggle('hidden',!open); $('menu-toggle').setAttribute('aria-expanded',String(open)); }
function openDialog(title, html, onReady) {
  $('dialog-title').textContent=title; $('dialog-content').innerHTML=html;
  if(!$('app-dialog').open) $('app-dialog').showModal();
  if(onReady) onReady($('dialog-content'));
}
function closeDialog() { $('app-dialog').close(); $('dialog-content').replaceChildren(); }
function confirmDialog(title, text, action, label='Confirmar', danger=false) {
  openDialog(title,`<p>${escapeHtml(text)}</p><div class="dialog-actions"><button type="button" id="confirm-cancel" class="btn secondary">Cancelar</button><button type="button" id="confirm-do" class="btn ${danger?'danger':'primary'}">${escapeHtml(label)}</button></div><div id="confirm-error" class="notice error hidden" role="alert"></div>`,()=>{
    $('confirm-cancel').onclick=closeDialog;
    $('confirm-do').onclick=()=>busy($('confirm-do'),async()=>{await action();closeDialog();},$('confirm-error'));
  });
}

function showAuth(setup=S.setup) {
  S.setup=setup; $('app-shell').classList.add('hidden'); $('auth-view').classList.remove('hidden'); setMenu(false);
  $('auth-name-wrap').classList.toggle('hidden',!setup); $('auth-name').required=setup;
  $('auth-title').textContent=setup?'Prepara tu laboratorio':'Bienvenido de nuevo';
  $('auth-description').textContent=setup?'Crea el primer acceso de administración. Tú eliges la contraseña.':S.publicDemo?'Explora los resultados o registra una actividad con los accesos de prueba.':'Accede con el usuario asignado por tu supervisor.';
  $('auth-submit').textContent=setup?'Crear mi acceso →':'Entrar al sistema →';
  $('auth-password').minLength=setup?10:1; $('auth-password').autocomplete=setup?'new-password':'current-password';
  $('auth-help').textContent=setup?'La contraseña de administración debe tener al menos 10 caracteres y ser distinta del usuario.':S.publicDemo?'Todos los accesos y registros de esta demostración son de prueba.':'¿Olvidaste tu contraseña? Tu supervisor puede restablecer tu acceso.';
  $('auth-mode-info').textContent=setup
    ? 'Primera configuración: crea aquí tu usuario y contraseña de administración.'
    : S.publicDemo
      ? 'Demostración pública con datos ficticios. Elige un acceso de prueba y pulsa Entrar al sistema.'
      : S.demo
      ? 'Estás en la demostración. Completa un acceso de prueba con los botones de abajo y pulsa Entrar al sistema.'
      : 'Instalación normal: usa la cuenta que creaste aquí o la que te asignó tu supervisor. Para probar con cuentas de ejemplo, abre probar_demo.bat.';
  $('demo-login-info').classList.toggle('hidden',!S.demo || setup);
  $('demo-login-info').replaceChildren();
  if(S.demo && !setup) $('demo-login-info').innerHTML=S.publicDemo
    ? '<strong>Demostración pública · Datos ficticios</strong><p>Resultados: <b>visitante_demo</b> / <b>VisitanteDemo2026!</b><br>Captura: <b>90001</b> / <b>90001</b></p><button type="button" class="text-button" id="fill-demo">Ver resultados →</button><br><button type="button" class="text-button" id="fill-demo-technician">Probar captura →</button>'
    : '<strong>Demostración con datos ficticios</strong><p>Supervisión: <b>supervisor_demo</b> / <b>LaboratorioDemo2026!</b><br>Colaborador: <b>90001</b> / <b>90001</b></p><button type="button" class="text-button" id="fill-demo">Usar acceso de supervisión →</button><br><button type="button" class="text-button" id="fill-demo-technician">Usar acceso de colaborador →</button><p>Si cambiaste una clave de la demo, usa tu clave actual.</p>';
  if($('fill-demo')) $('fill-demo').onclick=()=>{ $('auth-username').value=S.publicDemo?'visitante_demo':'supervisor_demo'; $('auth-password').value=S.publicDemo?'VisitanteDemo2026!':'LaboratorioDemo2026!'; $('auth-submit').focus(); };
  if($('fill-demo-technician')) $('fill-demo-technician').onclick=()=>{ $('auth-username').value='90001'; $('auth-password').value='90001'; $('auth-submit').focus(); };
}
async function loadReferences() {
  const results=await Promise.all([api('/api/actividades'),api('/api/catalogos'),api('/api/sap'),isVisitor()?Promise.resolve({users:[]}):api('/api/usuarios')]);
  S.activities=results[0].activities || []; S.catalog=results[1]; S.sap=results[2].items || []; S.users=results[3].users || [];
  const current=$('filter-activity').value;
  $('filter-activity').innerHTML=options(S.activities.map((a)=>({value:a.id,label:a.name})),current,'Todas las actividades');
  const people=personOptions().map((u)=>({value:u.id,label:u.name}));
  $('filter-responsible').innerHTML=options(people,$('filter-responsible').value,'Todo el equipo');
  $('capture-responsible').innerHTML=options(people,$('capture-responsible').value || S.user?.id,null);
  $('goal-responsible').innerHTML=options(people,$('goal-responsible').value,'Selecciona colaborador');
  $('goal-activity').innerHTML=options(activeActivities().map((a)=>({value:a.id,label:a.name})),$('goal-activity').value,'Selecciona actividad');
  $('filter-voltage').innerHTML=options(S.catalog.voltajes || [],$('filter-voltage').value,'Todos');
  $('filter-condition').innerHTML=options(S.catalog.condiciones || [],$('filter-condition').value,'Todas');
  $('voltage-list').innerHTML=(S.catalog.voltajes || []).map((x)=>`<option value="${escapeHtml(x)}"></option>`).join('');
  $('brands-list').innerHTML=(S.catalog.marcas || []).map((x)=>`<option value="${escapeHtml(x)}"></option>`).join('');
  $('sap-list').innerHTML=S.sap.filter((x)=>x.active).map((x)=>`<option value="${escapeHtml(x.code)}">${escapeHtml(x.voltage)} · ${escapeHtml(x.classification)}</option>`).join('');
}
async function enterApp(me) {
  S.user=me.user; S.csrf=me.csrf; S.demo=Boolean(me.demo); S.publicDemo=Boolean(me.public_demo); $('auth-view').classList.add('hidden'); $('app-shell').classList.remove('hidden');
  $('account-name').textContent=S.user.name; $('account-role').textContent=roleNames[S.user.role] || S.user.role;
  $('account-avatar').textContent=S.user.name.split(/\s+/).slice(0,2).map((n)=>n[0]).join('').toUpperCase();
  $('demo-badge').textContent=S.demo?'DATOS DE PRUEBA':'PRUEBA LOCAL'; $('environment-label').textContent=S.publicDemo?'Demostración pública':S.demo?'Demostración':'Versión de pruebas';
  setRoleVisibility(); if(!S.user.must_change) await loadReferences();
  if(S.user.must_change) { await navigate('account'); toast('Elige tu contraseña personal para continuar.','warning'); }
  else await navigate('dashboard');
}
function filterQuery(extra={}) {
  const q=new URLSearchParams();
  for(const [key,id] of [['desde','filter-from'],['hasta','filter-to'],['activity_id','filter-activity'],['sap','filter-sap'],['voltage','filter-voltage'],['brand','filter-brand'],['model','filter-model'],['condition','filter-condition']]) if($(id).value.trim()) q.set(key,$(id).value.trim());
  if(isManager() && $('filter-responsible').value) q.set('responsible_id',$('filter-responsible').value);
  Object.entries(extra).forEach(([key,value])=>{if(value!=='' && value!==undefined && value!==null) q.set(key,String(value));});
  return q.toString();
}
async function navigate(view) {
  if(!pages[view]) view='dashboard';
  if(!isManager() && ['activities','import','catalogs','users','audit'].includes(view)) view='dashboard';
  if(isVisitor() && !['dashboard','quality','comparison','account'].includes(view)) view='dashboard';
  if(S.user?.must_change && view!=='account') view='account';
  S.view=view; const ticket=++S.navigation; setMenu(false); clearError($('page-error'));
  document.querySelectorAll('.view').forEach((n)=>n.classList.add('hidden')); $(`view-${view}`).classList.remove('hidden');
  document.querySelectorAll('[data-view]').forEach((n)=>n.classList.toggle('active',n.dataset.view===view));
  const title=pages[view]; $('page-eyebrow').textContent=title[0]; $('page-title').textContent=title[1]; $('page-description').textContent=title[2]; $('current-section').textContent=title[1];
  $('global-filters').classList.toggle('hidden',!['dashboard','records','quality','comparison','receipts'].includes(view)); $('quick-capture').classList.toggle('hidden',isVisitor() || view==='capture' || S.user?.must_change);
  $('filter-from-wrap').classList.toggle('hidden',view==='comparison' || view==='receipts');$('filter-to-wrap').classList.toggle('hidden',view==='comparison' || view==='receipts');$('filter-activity-wrap').classList.toggle('hidden',view==='quality' || view==='receipts');
  $('loading-indicator').classList.remove('hidden');
  try { await ({dashboard:loadDashboard,quality:loadQuality,comparison:loadComparison,capture:loadCapture,records:loadRecords,history:async()=>{},activities:loadActivities,import:loadImport,receipts:loadReceipts,goals:loadGoals,users:loadUsers,catalogs:loadCatalogs,audit:loadAudit,account:loadAccount}[view])(); }
  catch(error) { if(ticket===S.navigation) showError($('page-error'),error); }
  finally { if(ticket===S.navigation) $('loading-indicator').classList.add('hidden'); }
}

function svgChart(id, data, title, unit='registros') {
  if(!data?.length || !data.some((x)=>Number(x.value))) { delete S.charts[id.replace('chart-','')];$(id).innerHTML=empty('Los datos aparecerán cuando haya actividad en este período.','Aún no hay datos'); return; }
  const rows=data.slice(0,12), width=Math.max(300,Math.min(650,$(id).clientWidth || 650)), barWidth=width-72, valueX=width-4, rowHeight=47, footerLines=chartFooter(`${chartContext()}${data.length>12?` · Se muestran 12 de ${data.length} categorías`:''}`,Math.floor(width/5)), height=68+rows.length*rowHeight+Math.max(0,footerLines.length-1)*13, max=Math.max(...rows.map((r)=>Number(r.value)||0),1);
  const chartRows=rows.map((row,i)=>{const y=36+i*rowHeight;const value=Number(row.value)||0;const label=String(row.label || 'Sin informar');const shortened=label.length>32?`${label.slice(0,31)}…`:label;const color=id==='chart-quality-results'?['#53d6a0','#ff8b95','#f7d47a','#93a4bd'][i]:(i===0?'#ed8a24':'#73a5e7');return `<g><title>${escapeHtml(label)}: ${escapeHtml(fmt(value))} ${escapeHtml(row.unit || unit)}</title><text x="0" y="${y}" fill="#afbed1" font-family="Arial,sans-serif" font-size="12">${escapeHtml(shortened)}</text><text x="${valueX}" y="${y}" text-anchor="end" fill="#8b9fb8" font-family="Arial,sans-serif" font-size="10">${escapeHtml(row.unit || unit)}</text><rect x="0" y="${y+9}" width="${barWidth}" height="10" rx="5" fill="#26364c"/><rect x="0" y="${y+9}" width="${Math.max(0,barWidth*value/max)}" height="10" rx="5" fill="${color}"/><text x="${valueX}" y="${y+16}" text-anchor="end" fill="#e6edf7" font-family="Arial,sans-serif" font-size="12" font-weight="bold">${escapeHtml(fmt(value))}</text></g>`;}).join('');
  const svg=`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" class="chart-svg" role="img" aria-label="${escapeHtml(title)}"><title>${escapeHtml(title)}</title><rect width="${width}" height="${height}" fill="#142238"/><text x="0" y="16" fill="#e6edf7" font-family="Arial,sans-serif" font-size="13" font-weight="bold">${escapeHtml(title)}</text>${chartRows}${footerLines.map((line,i)=>`<text x="0" y="${60+rows.length*rowHeight+i*13}" fill="#8b9fb8" font-family="Arial,sans-serif" font-size="9">${escapeHtml(line)}</text>`).join('')}</svg>`;
  $(id).innerHTML=svg; S.charts[id.replace('chart-','')]={svg,title,data,unit};
}
function chartContext() { const from=$('filter-from').value,to=$('filter-to').value;const scope=[`${from || 'Todo el historial'}${to?' al '+to:''}`,S.user?.role==='tecnico'?'Producción propia':'Laboratorio de Medidas'];if(S.view==='quality')scope.push('Actividad: Revisión técnica');for(const [id,label] of [['filter-activity','Actividad'],['filter-responsible','Responsable'],['filter-sap','SAP'],['filter-voltage','Voltaje'],['filter-brand','Marca'],['filter-model','Modelo'],['filter-condition','Condición']]){const input=$(id);if(!input.value || id==='filter-responsible'&&!isManager() || S.view==='quality'&&id==='filter-activity')continue;scope.push(`${label}: ${input.tagName==='SELECT'?input.selectedOptions[0]?.textContent:input.value}`);}return scope.join(' · '); }
function chartFooter(text,limit) {const words=text.split(/\s+/),lines=[];let line='';for(let word of words){while(word.length>limit){if(line){lines.push(line);line='';}lines.push(word.slice(0,limit));word=word.slice(limit);}if((line+' '+word).trim().length>limit){lines.push(line);line=word;}else line=(line+' '+word).trim();}if(line)lines.push(line);return lines;}
async function loadDashboard() {
  const data=await api(`/api/dashboard?${filterQuery()}`);
  const cards=[['Registros del período',data.event_count,'Eventos de todas las actividades','▤',''],['Revisiones técnicas',data.review_count,'Una revisión por medidor','⌕','accent'],['Series identificadas',data.identified_unique,'Únicas entre registros con serie','◈',''],['Reingresos de revisión',data.reentries,'Revisiones adicionales en el período','↶',''],['Recepciones pendientes',data.receipts_pending,'Lotes pendientes al corte','⇣','']];
  $('metrics-grid').innerHTML=cards.map(([label,value,note,icon,tone])=>`<article class="metric-card ${tone}"><div class="metric-top"><span class="metric-label">${escapeHtml(label)}</span><span class="metric-icon" aria-hidden="true">${icon}</span></div><strong class="metric-value">${fmt(value)}</strong><span class="metric-note">${escapeHtml(note)}</span></article>`).join('');
  $('unit-summary').innerHTML=Object.entries(data.totals_by_unit || {}).map(([unit,value])=>`<span class="unit-chip"><strong>${fmt(value)}</strong> ${escapeHtml(unit)} procesados</span>`).join('')+'<span class="muted">Las cantidades se presentan por unidad; los lotes no permiten contar equipos únicos.</span>';
  svgChart('chart-activity',data.by_activity,'Producción por actividad','unidades'); svgChart('chart-day',data.by_day,'Registros por día'); svgChart('chart-voltage',data.by_voltage,'Registros por voltaje'); if(isManager()) svgChart('chart-collaborator',data.by_collaborator,'Registros por colaborador');
  $('dashboard-goals').innerHTML=renderGoals(data.goals || [],true);
}
function metricCards(items) {
  return items.map(([label,value,note,tone=''])=>`<article class="metric-card ${escapeHtml(tone)}"><span class="metric-label">${escapeHtml(label)}</span><strong class="metric-value">${value===null || value===undefined?'—':typeof value==='string'?escapeHtml(value):fmt(value)}</strong><span class="metric-note">${escapeHtml(note || '')}</span></article>`).join('');
}
function signalBadge(signal,label) {
  const color=signal==='verde'?'good':signal==='rojo'?'danger':'warn',icon=signal==='verde'?'🟢':signal==='rojo'?'🔴':'🟡';
  return `<span class="badge ${color} operational-signal"><span aria-hidden="true">${icon}</span>${escapeHtml(label)}</span>`;
}
function percent(value) {return value===null || value===undefined?'—':`${fmt(value)} %`;}
function signed(value) {return value>0?`+${fmt(value)}`:fmt(value);}
function variation(value,state) {return value===null || state==='sin_base'?'Sin base':`${signed(value)} %`;}
function granularityLabel(value) {return ({diaria:'Diaria',semanal:'Semanal · semana ISO',mensual:'Mensual',anual:'Anual'})[value] || value;}
async function loadQuality() {
  const query=new URLSearchParams(filterQuery({granularity:$('quality-granularity').value}));query.delete('activity_id');
  const data=await api(`/api/calidad?${query}`),summary=data.summary;
  $('quality-status').innerHTML=signalBadge(summary.traffic_light,summary.traffic_light==='rojo'?'Hay rechazos o mediciones fuera de tolerancia':summary.traffic_light==='verde'?'Evaluaciones aprobadas':'Revisar pendientes o datos sin evaluación');
  $('quality-metrics').innerHTML=metricCards([
    ['Revisiones técnicas',summary.total,'Registros válidos en el período'],['Evaluaciones concluidas',summary.evaluated,'Apto + No apto'],
    ['Tasa de aprobación',percent(summary.approval_rate),`${fmt(summary.approved)} aprobadas / ${fmt(summary.evaluated)} evaluadas`,'positive'],['Tasa de rechazo',percent(summary.rejection_rate),`${fmt(summary.rejected)} rechazadas / ${fmt(summary.evaluated)} evaluadas`],
    ['Mediciones de calibración',summary.calibrations,'Con referencia y medición registradas'],['Fuera de tolerancia',summary.calibrations_outside_tolerance,'Desviación absoluta superior al límite'],
    ['Desviación media',percent(summary.mean_deviation_pct),'Promedio de las desviaciones con signo'],['Desviación absoluta media',percent(summary.mean_absolute_deviation_pct),'Promedio de la magnitud del error']]);
  $('quality-denominator').textContent=`Las tasas usan ${fmt(summary.evaluated)} evaluaciones concluidas. Pendientes: ${fmt(summary.pending)}. Sin resultado: ${fmt(summary.without_result)}. Los registros sin decisión no se cuentan como aprobados ni rechazados. El semáforo es rojo si hay rechazos o mediciones fuera de tolerancia; amarillo si faltan resultados; verde si las evaluaciones están aprobadas.`;
  svgChart('chart-quality-results',[{label:'Aprobadas',value:summary.approved},{label:'Rechazadas',value:summary.rejected},{label:'Pendientes',value:summary.pending},{label:'Sin resultado',value:summary.without_result}],'Resultados de revisión técnica');
  svgChart('chart-quality-failures',data.by_failure || [],'Fallos detectados');
  $('quality-technicians').innerHTML=table(['Técnico','Revisiones / evaluadas','Aprobación','Rechazo','Pendientes / sin resultado','Calibraciones','Fuera de tolerancia','Desviación media','Desviación absoluta media'],(data.by_technician || []).map((row)=>[
    `<strong>${escapeHtml(row.name)}</strong><small>${escapeHtml(row.username || '')}</small>`,`${fmt(row.total)} / ${fmt(row.evaluated)}`,percent(row.approval_rate),percent(row.rejection_rate),`${fmt(row.pending)} / ${fmt(row.without_result)}`,fmt(row.calibrations),row.calibrations_outside_tolerance?signalBadge('rojo',fmt(row.calibrations_outside_tolerance)):fmt(0),percent(row.mean_deviation_pct),percent(row.mean_absolute_deviation_pct)]));
  $('quality-period-label').textContent=`${granularityLabel(data.period?.granularity || $('quality-granularity').value)} · ${data.period?.desde || $('filter-from').value || 'Inicio del historial'} al ${data.period?.hasta || $('filter-to').value || today()}`;
  $('quality-timeline').innerHTML=table(['Intervalo','Revisiones','Aprobadas','Rechazadas','Pendientes','Sin resultado','Aprobación','Fuera de tolerancia'],(data.by_period || []).map((row)=>[escapeHtml(row.label),fmt(row.total),fmt(row.approved),fmt(row.rejected),fmt(row.pending),fmt(row.without_result),percent(row.approval_rate),fmt(row.calibrations_outside_tolerance)]));
  for(const format of ['xlsx','pdf'])$(`quality-export-${format}`).href=`/api/calidad.${format}?${query}`;
}
function comparisonChart(data) {
  const container=$('chart-comparison'),rows=(data.rows || []).slice(0,12);
  if(!rows.length){delete S.charts.comparison;container.innerHTML=empty('La comparación aparecerá cuando haya producción en alguno de los períodos.','Sin actividad para comparar');return;}
  const width=Math.max(330,Math.min(760,container.clientWidth || 760)),barWidth=width-90,valueX=width-3,rowHeight=78;
  const context=`A: ${data.period_a.from} al ${data.period_a.to} · B: ${data.period_b.from} al ${data.period_b.to} · ${S.user?.role==='tecnico'?'Producción propia':'Laboratorio de Medidas'}${data.rows.length>12?` · Se muestran 12 de ${data.rows.length} filas`:''}`;
  const filters=[['filter-activity','Actividad'],['filter-responsible','Colaborador'],['filter-sap','SAP'],['filter-voltage','Voltaje'],['filter-brand','Marca'],['filter-model','Modelo'],['filter-condition','Condición']].filter(([id])=>$(id).value && (id!=='filter-responsible' || isManager())).map(([id,label])=>`${label}: ${$(id).tagName==='SELECT'?$(id).selectedOptions[0].textContent:$(id).value}`).join(' · ');
  const footer=chartFooter([context,filters,'Escala independiente por fila: compara A y B dentro de la misma actividad y unidad.'].filter(Boolean).join(' · '),Math.floor(width/5.1));
  const height=70+rows.length*rowHeight+footer.length*13;
  const bars=rows.map((row,index)=>{const y=51+index*rowHeight,max=Math.max(row.a,row.b,1),label=`${row.activity_name} · ${row.unit}`,shortened=label.length>Math.floor(width/7)?label.slice(0,Math.floor(width/7)-1)+'…':label;return `<g><title>${escapeHtml(label)}: A ${fmt(row.a)}, B ${fmt(row.b)}</title><text x="0" y="${y}" fill="#cfdef3" font-size="12">${escapeHtml(shortened)}</text><text x="0" y="${y+23}" fill="#a8caf4" font-size="10">A</text><rect x="17" y="${y+13}" width="${barWidth}" height="12" rx="3" fill="#22344d"/><rect x="17" y="${y+13}" width="${barWidth*row.a/max}" height="12" rx="3" fill="#73a5e7"/><text x="${valueX}" y="${y+23}" fill="#d7e8ff" font-size="12" text-anchor="end">${escapeHtml(fmt(row.a))}</text><text x="0" y="${y+45}" fill="#ffc286" font-size="10">B</text><rect x="17" y="${y+35}" width="${barWidth}" height="12" rx="3" fill="#22344d"/><rect x="17" y="${y+35}" width="${barWidth*row.b/max}" height="12" rx="3" fill="#ef9a49"/><text x="${valueX}" y="${y+45}" fill="#ffe0bc" font-size="12" text-anchor="end">${escapeHtml(fmt(row.b))}</text></g>`;}).join('');
  const svg=`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" class="chart-svg" font-family="Arial,sans-serif" role="img" aria-label="Comparación A y B por actividad y unidad"><title>Comparación A y B por actividad y unidad</title><rect width="${width}" height="${height}" fill="#142238"/><text x="0" y="18" fill="#edf4ff" font-size="13" font-weight="bold">Comparación A / B · actividad y unidad</text>${bars}${footer.map((line,index)=>`<text x="0" y="${65+rows.length*rowHeight+index*13}" fill="#a5b8d2" font-size="9">${escapeHtml(line)}</text>`).join('')}</svg>`;
  container.innerHTML=svg;S.charts.comparison={svg,title:'Comparación A y B',data:rows,unit:'unidades'};
}

function setComparisonDefaults() {
  const day=today(),end=new Date(`${day}T12:00:00Z`),start=new Date(Date.UTC(end.getUTCFullYear(),end.getUTCMonth(),1,12)),previousEnd=new Date(start.valueOf()-86400000),duration=Math.round((end-start)/86400000),previousStart=new Date(previousEnd.valueOf()-duration*86400000);
  const iso=(value)=>value.toISOString().slice(0,10);
  $('comparison-a-from').value=iso(previousStart);$('comparison-a-to').value=iso(previousEnd);$('comparison-b-from').value=iso(start);$('comparison-b-to').value=day;
}
function comparisonQuery() {
  const query=new URLSearchParams(filterQuery());query.delete('desde');query.delete('hasta');
  for(const [name,id] of [['a_desde','comparison-a-from'],['a_hasta','comparison-a-to'],['b_desde','comparison-b-from'],['b_hasta','comparison-b-to'],['granularity','comparison-granularity']])query.set(name,$(id).value);
  if(!query.get('a_desde') || !query.get('a_hasta') || !query.get('b_desde') || !query.get('b_hasta'))throw new Error('Completa las cuatro fechas de los períodos.');
  if(query.get('a_desde')>query.get('a_hasta') || query.get('b_desde')>query.get('b_hasta'))throw new Error('La fecha inicial de cada período debe ser anterior o igual a su fecha final.');
  return query;
}
async function loadComparison() {
  const query=comparisonQuery(),data=await api(`/api/comparativas?${query}`),summary=data.summary;clearError($('comparison-error'));
  $('comparison-metrics').innerHTML=metricCards([
    ['Registros del período A',summary.records_a,'Base de la comparación'],['Registros del período B',summary.records_b,'Período comparado'],
    ['Variación absoluta',signed(summary.delta_records),'Registros de B − registros de A'],['Variación porcentual',variation(summary.percent_records,summary.percent_state),'(B − A) / A × 100']]);
  $('comparison-periods').textContent=`A: ${prettyDate(data.period_a.from)} — ${prettyDate(data.period_a.to)} (${fmt(data.period_a.days)} días). B: ${prettyDate(data.period_b.from)} — ${prettyDate(data.period_b.to)} (${fmt(data.period_b.days)} días). ${data.period_a.days!==data.period_b.days?'Los períodos tienen distinta duración; las cantidades no se normalizan por día.':'Ambos períodos tienen la misma duración.'}`;
  $('comparison-table').innerHTML=table(['Actividad','Unidad','Cantidad A','Cantidad B','Variación absoluta','Variación %','Registros A / B'],(data.rows || []).map((row)=>[
    `<strong>${escapeHtml(row.activity_name)}</strong>`,escapeHtml(row.unit),fmt(row.a),fmt(row.b),`<span class="numeric-change ${row.delta<0?'negative':row.delta>0?'positive':''}">${escapeHtml(signed(row.delta))}</span>`,escapeHtml(variation(row.percent,row.percent_state)),`${fmt(row.records_a)} / ${fmt(row.records_b)}`]),'Ninguna actividad tiene registros en estos períodos y filtros.');
  const seriesTable=(rows)=>table(['Intervalo','Registros','Cantidades por unidad'],rows.map((row)=>[escapeHtml(row.label),fmt(row.records),Object.entries(row.totals_by_unit || {}).map(([unit,value])=>`${fmt(value)} ${escapeHtml(unit)}`).join('<br>') || '—']));
  $('comparison-series-a').innerHTML=seriesTable(data.series_a || []);$('comparison-series-b').innerHTML=seriesTable(data.series_b || []);
  S.comparison=data;comparisonChart(data);
  for(const format of ['xlsx','pdf'])$(`comparison-export-${format}`).href=`/api/comparativas.${format}?${query}`;
}

function progress(value) { if(value===null || value===undefined) return '<span class="muted">Sin meta</span>'; const n=Number(value)||0;return `<div class="progress-cell"><progress max="100" value="${Math.min(100,Math.max(0,n))}" aria-label="Cumplimiento ${escapeHtml(fmt(n))} por ciento"></progress><strong>${fmt(n)}%</strong></div>`; }
function downloadBlob(blob,name) { const link=document.createElement('a');const url=URL.createObjectURL(blob);link.href=url;link.download=name;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1500); }
async function exportChart(key, format, button) {
  const chart=S.charts[key]; if(!chart) return toast('Este gráfico aún no tiene datos para descargar.','warning');
  await busy(button,async()=>{
    const name=`laboratorio-${key}-${today()}`;
    if(format==='svg') return downloadBlob(new Blob([chart.svg],{type:'image/svg+xml;charset=utf-8'}),`${name}.svg`);
    const image=new Image(); image.src=`data:image/svg+xml;charset=utf-8,${encodeURIComponent(chart.svg)}`; await image.decode();
    const viewBox=new DOMParser().parseFromString(chart.svg,'image/svg+xml').documentElement.getAttribute('viewBox').split(' ').map(Number);
    const canvas=document.createElement('canvas'); canvas.width=viewBox[2]*2; canvas.height=viewBox[3]*2; const ctx=canvas.getContext('2d');ctx.scale(2,2);ctx.drawImage(image,0,0);
    const blob=await new Promise((resolve)=>canvas.toBlob(resolve,'image/png')); if(!blob) throw new Error('No se pudo preparar la imagen. Prueba el formato SVG.');downloadBlob(blob,`${name}.png`);
  });
}

function savedPin() { try{return JSON.parse(localStorage.getItem(`lab-pin-${S.user.id}`)||'null');}catch(_){return null;} }
function storePin() { try {if($('pin-activity').checked)localStorage.setItem(`lab-pin-${S.user.id}`,JSON.stringify($('capture-activity').value));else localStorage.removeItem(`lab-pin-${S.user.id}`);}catch(_){} }
async function loadCapture() {
  const allowed=activeActivities(); const pin=savedPin(); const previous=$('capture-activity').value;
  $('capture-activity').innerHTML=options(allowed.map((a)=>({value:a.id,label:a.name})),allowed.some((a)=>a.id===pin)?pin:previous,null);
  $('pin-activity').checked=Boolean(pin && allowed.some((a)=>a.id===pin));
  if(!$('capture-date').value)$('capture-date').value=today();
  $('capture-submit').disabled=!allowed.length;
  if(!allowed.length) {$('capture-fields').innerHTML=empty('Pide al supervisor que habilite una actividad para tu cuenta.','Sin actividades asignadas');$('capture-context').textContent='No tienes actividades activas para registrar.';}
  else renderCaptureFields();
  const recent=await api('/api/eventos?page=1&page_size=5');
  $('recent-records').innerHTML=(recent.records || []).map((r)=>`<div class="recent-item"><div class="recent-top"><strong>${escapeHtml(r.activity_name)}</strong><span>${fmt(r.quantity)} ${escapeHtml(r.unit)}</span></div><p>${escapeHtml(r.data?.serie ? `Serie ${r.data.serie}` : r.data?.sap ? `SAP ${r.data.sap}` : 'Registro por cantidad')}</p><span class="recent-meta">${escapeHtml(prettyDate(r.work_date))} · ${escapeHtml(r.responsible_name)}</span></div>`).join('') || empty('Tus próximas capturas aparecerán aquí.','Listo para comenzar');
}
function optionsFor(field) { if(Array.isArray(field.options) && field.options.length) return field.options; if(field.key==='voltaje')return S.catalog.voltajes || [];if(field.key==='condicion')return S.catalog.condiciones || [];return []; }
function fieldHtml(field, value='', prefix='capture') {
  const key=field.key; const id=`${prefix}-field-${key}`; const required=field.required && !['checkbox','casilla'].includes(field.type)?' required':''; const common=`id="${escapeHtml(id)}" data-field="${escapeHtml(key)}"${required}`;
  const title=`${escapeHtml(field.label || labels[key] || key)}${field.required?' <span class="required-dot" aria-label="obligatorio">*</span>':' <small>Opcional</small>'}`;
  const type=field.type || 'text'; let input;
  if(key==='sap_config_id') input=`<select ${common}>${options(S.sap.flatMap((item)=>(item.configurations || []).map((config)=>({value:config.id,label:`${item.code} · ${config.label || config.voltage || 'Sin voltaje'} · ${config.classification || 'Sin clasificación'}`}))),value,'Automática si es inequívoca')}</select>`;
  else if(key==='clasificacion' && prefix==='capture' && $('capture-activity').value==='sellado') input=`<input id="${escapeHtml(id)}" data-field="clasificacion" value="${escapeHtml(value)}" readonly placeholder="Se determina con el código SAP" aria-label="Clasificación automática por SAP">`;
  else if(['select','seleccion'].includes(type)) input=`<select ${common}>${options(optionsFor(field),value)}</select>`;
  else if(['checkbox','casilla'].includes(type)) input=`<input ${common} type="checkbox"${value===true?' checked':''}>`;
  else if(key==='observaciones' || type==='textarea') input=`<textarea ${common} rows="3" maxlength="1500">${escapeHtml(value)}</textarea>`;
  else { const inputType=['number','numero'].includes(type)?'number':['date','fecha'].includes(type)?'date':'text'; input=`<input ${common} type="${inputType}" value="${escapeHtml(value)}"${inputType==='number'?` ${field.min!==undefined?`min="${escapeHtml(field.min)}"`:''} ${field.max!==undefined?`max="${escapeHtml(field.max)}"`:''} step="${field.integer?'1':'any'}"`:''}${key==='marca'?' list="brands-list"':''}${key==='sap'?' list="sap-list"':''}${key==='serie'?' autocomplete="off" maxlength="60"':''}${key==='sap'?' maxlength="60"':''}>`; }
  return `<label class="${key==='observaciones'?'full-width':''}${['checkbox','casilla'].includes(type)?' checkbox-label':''}"><span class="label-text">${title}</span>${input}</label>`;
}
function renderCaptureFields() {
  const activity=S.activities.find((a)=>a.id===$('capture-activity').value); if(!activity)return;
  if(isManager()) { const selected=$('capture-responsible').value;const eligible=personOptions().filter((u)=>['supervisor','administrador'].includes(u.role) || (u.activity_ids || []).includes(activity.id));const current=eligible.some((u)=>String(u.id)===selected)?selected:eligible.some((u)=>u.id===S.user.id)?S.user.id:'';$('capture-responsible').innerHTML=options(eligible.map((u)=>({value:u.id,label:u.name})),current,null); }
  clearError($('capture-error')); $('capture-fields').innerHTML=activity.fields.map((f)=>fieldHtml(f)).join('');
  $('activity-mode-badge').textContent=modeNames[activity.mode] || activity.mode;
  $('capture-context').textContent=activity.mode==='individual'?'Cada guardado corresponde a un medidor. Conserva su serie exacta.':activity.mode==='recepcion'?'Registra esta entrega; se acumulará a las anteriores de la orden.':'Registra la cantidad trabajada y los datos del lote.';
  $('capture-quantity').readOnly=activity.mode==='individual'; if(activity.mode==='individual')$('capture-quantity').value='1';
  $('recorded-by-hint').textContent=`Capturado por ${S.user.name}. El responsable y el historial quedarán registrados.`;
  $('sap-hint').classList.add('hidden');
  const sap=$('capture-field-sap'); if(sap)sap.addEventListener('change',()=>updateSapHint(true));
  const configuration=$('capture-field-sap_config_id');if(configuration)configuration.addEventListener('change',()=>updateSapHint(false));
  for(const key of ['valor_referencia','valor_medido','tolerancia_pct'])$(`capture-field-${key}`)?.addEventListener('input',updateCalibrationHint);
  S.operation=newOperation();
}
function setFieldValue(input,value) {
  if(!input)return;
  if(input.tagName==='SELECT' && value && ![...input.options].some((o)=>o.value===String(value))){const option=document.createElement('option');option.value=String(value);option.textContent=String(value);input.add(option);}
  input.value=String(value ?? '');
}
function updateSapHint(reset=false) {
  const value=$('capture-field-sap')?.value.trim(),hint=$('sap-hint'),select=$('capture-field-sap_config_id');
  const classification=$('capture-field-clasificacion'),voltage=$('capture-field-voltaje'),sealing=$('capture-activity').value==='sellado';
  if(!value){hint.classList.add('hidden');if(select)select.innerHTML=options([], '', 'Selecciona primero un SAP');if(sealing && classification)classification.value='';return;}
  const item=S.sap.find((x)=>String(x.code)===value && x.active);hint.classList.remove('hidden');
  if(!item){if(select)select.innerHTML=options([], '', 'SAP sin configurar');if(sealing && classification)classification.value='';hint.textContent='SAP aún no catalogado. Revisión técnica permite conservarlo como dato opcional. Configura el SAP para obtener la clasificación automática de sellado.';return;}
  const configs=(item.configurations?.length?item.configurations:[{...item,id:''}]).filter((config)=>config.active!==false && config.active!==0);
  const previous=reset?'':select?.value || '';
  let config=configs.find((c)=>String(c.id)===String(previous) && previous!=='');
  if(!config && configs.length===1)config=configs[0];
  if(!config && !reset){const matching=configs.filter((c)=>(!voltage?.value || c.voltage===voltage.value) && (!classification?.value || c.classification===classification.value));if(matching.length===1)config=matching[0];}
  if(select)select.innerHTML=options(configs.map((c)=>({value:c.id,label:[c.label,c.voltage,c.classification].filter(Boolean).join(' · ') || 'Configuración sin descripción'})),config?.id || previous,configs.length>1?'Selecciona la configuración':'Configuración automática');
  if(config){setFieldValue(voltage,config.voltage || voltage?.value || '');setFieldValue(classification,config.classification || '');const brand=$('capture-field-marca'),model=$('capture-field-modelo');if(brand && !brand.value)brand.value=config.brand || '';if(model && !model.value)model.value=config.model || '';hint.innerHTML=`${signalBadge('verde','Configuración identificada')} <strong>SAP ${escapeHtml(value)}</strong><p>${escapeHtml([config.voltage,config.classification,config.label].filter(Boolean).join(' · '))}. Marca y modelo son independientes. Recuperado describe el origen del medidor.</p>`;}
  else {if(sealing && classification)classification.value='';hint.innerHTML=`${signalBadge('amarillo','Selecciona una configuración')}<p>Este SAP admite ${fmt(configs.length)} configuraciones. Elige la correspondiente al medidor para determinar su clasificación.</p>`;}
}
function updateCalibrationHint() {
  const reference=$('capture-field-valor_referencia'),measured=$('capture-field-valor_medido'),tolerance=$('capture-field-tolerancia_pct');
  let result=$('capture-calibration-result');if(!reference || !measured)return;
  if(!result){result=document.createElement('div');result.id='capture-calibration-result';result.className='notice full-width';result.setAttribute('role','status');$('capture-fields').append(result);}
  if(reference.value==='' || measured.value===''){result.classList.add('hidden');return;}
  const ref=Number(reference.value),value=Number(measured.value),limit=Number(tolerance?.value);
  result.classList.remove('hidden');if(!Number.isFinite(ref) || !Number.isFinite(value) || ref===0){result.textContent='La referencia debe ser distinta de cero y las mediciones deben ser finitas.';return;}
  const deviation=(value-ref)/Math.abs(ref)*100,hasTolerance=tolerance?.value!=='' && Number.isFinite(limit) && limit>=0;
  result.innerHTML=`${signalBadge(hasTolerance && Math.abs(deviation)>limit?'rojo':hasTolerance?'verde':'amarillo',hasTolerance?(Math.abs(deviation)>limit?'Fuera de tolerancia':'Dentro de tolerancia'):'Tolerancia sin informar')}<p>Desviación: <strong>${fmt(deviation)} %</strong> · (medido − referencia) / |referencia| × 100. El sistema verificará el cálculo al guardar.</p>`;
}
function readFields(container) { const data={};container.querySelectorAll('[data-field]').forEach((input)=>{data[input.dataset.field]=input.type==='checkbox'?input.checked:input.type==='number'?(input.value===''?'':Number(input.value)):input.value.trim();});return data; }
async function saveCapture(confirmed=false, payload=null) {
  const activity=S.activities.find((a)=>a.id===$('capture-activity').value); if(!activity)throw new Error('Selecciona una actividad habilitada.');
  const data=payload || {activity_id:activity.id,work_date:$('capture-date').value,quantity:Number($('capture-quantity').value),data:readFields($('capture-fields')),operation_id:S.operation};
  if(isManager() && !data.responsible_id)data.responsible_id=Number($('capture-responsible').value);
  if(confirmed)data.confirm_reentry=true;
  try {
    const result=await api('/api/eventos',data); closeDialog(); storePin(); S.operation=newOperation();
    toast(`Actividad guardada · ${fmt(result.record?.quantity || data.quantity)} ${result.record?.unit || activity.unit}.`);
    ['serie','observaciones'].forEach((key)=>{const n=$(`capture-field-${key}`);if(n)n.value='';});
    if(activity.mode!=='individual')$('capture-quantity').value='1';
    await loadCapture();
    for(const [key,value] of Object.entries(data.data || {})) { if(['serie','observaciones'].includes(key))continue; const field=$(`capture-field-${key}`);if(field){if(field.type==='checkbox')field.checked=Boolean(value);else field.value=String(value ?? '');} }
    updateSapHint();
    if(activity.mode==='recepcion') toast('Entrega registrada. Revisa el saldo y las recepciones pendientes en Recepciones.','warning');
    $('capture-field-serie')?.focus();
  } catch(error) {
    if(error.status===409 && error.payload?.needs_confirmation) { showReentry(error.payload,()=>saveCapture(true,data));return; }
    throw error;
  }
}
function showReentry(details, action) {
  const rows=Array.isArray(details.previous)?details.previous:[];
  const heading=details.same_day?'Este medidor ya tiene un registro en la misma fecha':'Este medidor tiene antecedentes';
  const body=`<div class="notice ${details.same_day?'warning':'soft'}"><strong>${escapeHtml(heading)}</strong><p>Confirma que se trata del medidor correcto. Se creará un evento nuevo; el anterior se conserva.</p></div>${rows.length?table(['Fecha','Actividad','Condición','Responsable'],rows.slice(0,4).map((r)=>[escapeHtml(prettyDate(r.work_date)),escapeHtml(r.activity_name || 'Revisión'),escapeHtml(r.data?.condicion || r.condition || '—'),escapeHtml(r.responsible_name || r.name || 'Información de referencia')])):''}<div class="dialog-actions"><button id="reentry-cancel" class="btn secondary">Corregir datos</button><button id="reentry-confirm" class="btn primary">Confirmar nueva revisión</button></div><div id="reentry-error" class="notice error hidden" role="alert"></div>`;
  openDialog('Confirmar reingreso',body,()=>{ $('reentry-cancel').onclick=closeDialog;$('reentry-confirm').onclick=()=>busy($('reentry-confirm'),action,$('reentry-error')); });
}

function recordSummary(record) { const d=record.data || {};return d.serie ? `<strong class="mono">${escapeHtml(d.serie)}</strong>${d.sap?`<small>SAP ${escapeHtml(d.sap)}</small>`:''}` : d.sap?`<strong class="mono">SAP ${escapeHtml(d.sap)}</strong><small>${escapeHtml(d.destino || d.numero_orden || d.marca || '')}</small>`:escapeHtml(d.marca || 'Registro por lote'); }
function recordRows(records, actions=true) {return records.map((r)=>[escapeHtml(prettyDate(r.work_date)),`<strong>${escapeHtml(r.activity_name)}</strong><small>Versión ${escapeHtml(r.activity_version)}</small>`,recordSummary(r),`${fmt(r.quantity)}<small>${escapeHtml(r.unit)}</small>`,escapeHtml(r.responsible_name),badge(r.state==='anulado'?'Anulado':'Válido',r.state==='anulado'?'danger':'good'),actions?`<button class="mini-button" data-event="${r.id}" data-action="detail">Ver</button>${r.state==='anulado'?isManager()?`<button class="mini-button" data-event="${r.id}" data-action="restore">Restaurar</button>`:'':`<button class="mini-button" data-event="${r.id}" data-action="edit">Corregir</button><button class="mini-button danger-text" data-event="${r.id}" data-action="void">Anular</button>`}`:'']);}
async function loadRecords() {
  const q=filterQuery({meter:$('records-meter').value.trim(),state:$('records-state').value,page:S.page,page_size:20});
  const data=await api(`/api/eventos?${q}`);S.records=data.records || [];S.page=data.page || 1;S.pages=data.pages || 1;
  $('records-summary').textContent=`${fmt(data.total)} registros coinciden con los filtros.`;
  $('records-table').innerHTML=table(['Fecha','Actividad','Medidor / SAP','Cantidad','Responsable','Estado','Acciones'],recordRows(S.records));
  $('records-page-label').textContent=`Página ${S.page} de ${S.pages}`;$('records-prev').disabled=S.page<=1;$('records-next').disabled=S.page>=S.pages;
  ['csv','xlsx','pdf'].forEach((format)=>$(`export-${format}`).href=`/api/export.${format}?${filterQuery({meter:$('records-meter').value.trim(),state:$('records-state').value})}`);
}
function detailHtml(record) {
  const data=record.data || {};
  return `<div class="detail-title">${badge(record.activity_name)} ${badge(record.state==='anulado'?'Anulado':'Válido',record.state==='anulado'?'danger':'good')}</div><dl class="detail-list"><dt>Fecha de trabajo</dt><dd>${escapeHtml(prettyDate(record.work_date))}</dd><dt>Cantidad</dt><dd>${fmt(record.quantity)} ${escapeHtml(record.unit)}</dd><dt>Responsable</dt><dd>${escapeHtml(record.responsible_name)}</dd><dt>Registrado por</dt><dd>${escapeHtml(record.recorded_by_name)}</dd><dt>Fecha de captura</dt><dd>${escapeHtml(prettyTime(record.created_at))}</dd><dt>Versión del formulario</dt><dd>${escapeHtml(record.activity_version)}</dd>${Object.entries(data).filter(([,v])=>v!=='' && v!==null).map(([key,value])=>`<dt>${escapeHtml(labels[key] || key)}</dt><dd>${escapeHtml(value===true?'Sí':value===false?'No':value)}</dd>`).join('')}</dl>`;
}
function editRecord(record) {
  const activity=S.activities.find((a)=>a.id===record.activity_id);
  const fields=record.fields || (activity?.fields || []).filter((f)=>Object.hasOwn(record.data || {},f.key));
  const known=new Set(fields.map((f)=>f.key));
  Object.keys(record.data || {}).filter((key)=>!known.has(key)).forEach((key)=>fields.push({key,label:labels[key] || key,type:typeof record.data[key]==='number'?'number':'text',required:false}));
  openDialog('Corregir registro',`<form id="edit-record-form" class="dialog-form"><p class="muted">Se conservarán el registro anterior, el motivo y la persona que realiza esta corrección.</p><div class="form-grid two"><label>Fecha de trabajo<input id="edit-date" type="date" value="${escapeHtml(record.work_date)}" required></label><label>Cantidad<input id="edit-quantity" type="number" min="1" step="1" value="${record.quantity}" ${record.mode==='individual'?'readonly':''} required></label></div><div id="edit-fields" class="form-grid two">${fields.map((f)=>fieldHtml(f,record.data?.[f.key] ?? '','edit')).join('')}</div><label>Motivo de la corrección<textarea id="edit-reason" required minlength="3" maxlength="500" rows="2"></textarea></label><div class="notice error hidden" id="edit-error" role="alert"></div><div class="dialog-actions"><button type="button" class="btn secondary" id="edit-cancel">Cancelar</button><button class="btn primary" type="submit">Guardar corrección</button></div></form>`,()=>{
    $('edit-cancel').onclick=closeDialog;
    $('edit-record-form').onsubmit=(event)=>{event.preventDefault();busy(event.submitter,async()=>{await api(`/api/eventos/${record.id}/corregir`,{work_date:$('edit-date').value,quantity:Number($('edit-quantity').value),data:readFields($('edit-fields')),reason:$('edit-reason').value.trim()});closeDialog();toast('Corrección guardada con su historial.');await loadRecords();},$('edit-error'));};
  });
}
function changeRecordState(record, restore) {
  openDialog(restore?'Restaurar registro':'Anular registro',`<form id="state-form" class="dialog-form"><p>${restore?'El registro volverá a contar en los resultados.':'El registro se conservará en el historial y dejará de contar en la producción.'}</p><label>Motivo<textarea id="state-reason" required minlength="3" maxlength="500" rows="3"></textarea></label><div id="state-error" class="notice error hidden" role="alert"></div><div class="dialog-actions"><button type="button" id="state-cancel" class="btn secondary">Cancelar</button><button type="submit" class="btn ${restore?'primary':'danger'}">${restore?'Restaurar registro':'Confirmar anulación'}</button></div></form>`,()=>{
    $('state-cancel').onclick=closeDialog;$('state-form').onsubmit=(event)=>{event.preventDefault();busy(event.submitter,async()=>{await api(`/api/eventos/${record.id}/${restore?'restaurar':'anular'}`,{reason:$('state-reason').value.trim()});closeDialog();toast(restore?'Registro restaurado.':'Registro anulado; su historial se conserva.');await loadRecords();},$('state-error'));};
  });
}
async function searchHistory() {
  const data=await api(`/api/historial?medidor=${encodeURIComponent($('history-meter').value.trim())}`);
  $('history-results').innerHTML=`<div class="card-heading"><div><h2>Serie ${escapeHtml(data.meter)}</h2><p>${fmt(data.count)} registros autorizados en su historial.</p></div></div>${data.records?.length?`<div class="timeline">${data.records.map((r)=>`<article class="timeline-item"><div class="timeline-date">${escapeHtml(prettyDate(r.work_date))}</div>${detailHtml(r)}</article>`).join('')}</div>`:empty('No se encontraron registros autorizados para esta serie.','Sin antecedentes')}`;
}

async function loadActivities() {
  $('activities-grid').innerHTML=S.activities.map((a)=>`<article class="card activity-card"><div class="activity-header"><span class="activity-symbol" aria-hidden="true">${a.mode==='individual'?'⌕':a.mode==='recepcion'?'⇣':'◈'}</span>${badge(a.active?'Habilitada':'Desactivada',a.active?'good':'muted')}</div><h2>${escapeHtml(a.name)}</h2><p>${escapeHtml(modeNames[a.mode] || a.mode)} · ${escapeHtml(a.unit)}</p><div class="activity-fields">${a.fields.slice(0,5).map((f)=>`<span class="field-pill">${escapeHtml(f.label || labels[f.key] || f.key)}</span>`).join('')}${a.fields.length>5?`<span class="field-pill">+${a.fields.length-5}</span>`:''}</div><div class="activity-footer"><span class="muted">Versión ${a.version}</span><button class="btn small secondary" data-edit-activity="${escapeHtml(a.id)}">Configurar →</button></div></article>`).join('');
}
function slug(label) {return String(label).normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,'_').replace(/^_+|_+$/g,'').replace(/^(?=\d)/,'campo_').slice(0,40);}
function editActivity(activity=null) {
  let draft=(activity?.fields || [{key:'descripcion',label:'Descripción del trabajo',type:'text',required:true},{key:'observaciones',label:'Observaciones',type:'text',required:false}]).map((f)=>({...f}));
  openDialog(activity?'Configurar actividad':'Crear actividad',`<form id="activity-form" class="dialog-form"><div class="notice soft">Los cambios se aplican a nuevas capturas. Los registros anteriores conservan su versión.</div><label>Nombre de la actividad<input id="activity-name" required maxlength="120" value="${escapeHtml(activity?.name || '')}" placeholder="Nombre que verán los colaboradores"></label><div class="form-grid two"><label>Forma de registro<select id="activity-mode">${options([{value:'lote',label:'Por cantidad / lote'},{value:'individual',label:'Por medidor individual'},{value:'recepcion',label:'Recepción con entregas'}],activity?.mode || 'lote',null)}</select></label><label>Unidad de producción<input id="activity-unit" required maxlength="40" value="${escapeHtml(activity?.unit || 'medidores')}" placeholder="Medidores, sellos, revisiones…"></label></div><label class="checkbox-label"><input id="activity-active" type="checkbox" ${activity?.active===false?'':'checked'}> Actividad habilitada para nuevas capturas</label><div class="card-heading"><h3>Datos que solicitará el formulario</h3><button id="add-field" type="button" class="btn small secondary">＋ Añadir dato</button></div><p class="muted small-text">La fecha, la persona responsable y la cantidad ya se incluyen automáticamente.</p><div id="field-builder" class="field-builder"></div><div id="activity-error" class="notice error hidden" role="alert"></div><div class="dialog-actions"><button id="activity-cancel" type="button" class="btn secondary">Cancelar</button><button type="submit" class="btn primary">${activity?'Guardar nueva versión':'Crear actividad'}</button></div></form>`,()=>{
    const readDraft=()=>[...$('field-builder').querySelectorAll('.field-editor')].map((row)=>{const base=draft.find((field)=>field.key && field.key===row.dataset.key) || {};const field={...base,key:row.dataset.key || slug(row.querySelector('[data-part="label"]').value),label:row.querySelector('[data-part="label"]').value.trim(),type:row.querySelector('[data-part="type"]').value,required:row.querySelector('[data-part="required"]').checked,options:row.querySelector('[data-part="options"]').value.split(',').map((x)=>x.trim()).filter(Boolean)};if(field.type!=='select')delete field.source;return field;});
    const draw=()=>{$('field-builder').innerHTML=draft.map((f,i)=>`<div class="field-editor" data-key="${escapeHtml(f.key || '')}"><div class="field-editor-header"><strong>Dato ${i+1}</strong><button type="button" class="text-button danger-text" data-remove-field="${i}">Quitar</button></div><div class="form-grid two"><label>Nombre del dato<input data-part="label" required maxlength="80" value="${escapeHtml(f.label || '')}"></label><label>Tipo<select data-part="type">${options([{value:'text',label:'Texto'},{value:'number',label:'Número'},{value:'date',label:'Fecha'},{value:'select',label:'Lista de opciones'},{value:'checkbox',label:'Casilla sí / no'}],f.type || 'text',null)}</select></label></div><label class="${f.type==='select'?'':'hidden'}" data-options-wrap>Opciones, separadas por comas<input data-part="options" value="${escapeHtml((f.options || []).join(', '))}" placeholder="Opción uno, opción dos"></label><label class="checkbox-label"><input data-part="required" type="checkbox" ${f.required?'checked':''}> Obligatorio</label></div>`).join('');};
    draw();$('add-field').onclick=()=>{draft=readDraft();if(draft.length>=24)return toast('Puedes definir hasta 24 datos por actividad.','warning');draft.push({label:'',type:'text',required:false,options:[]});draw();};
    $('field-builder').onclick=(event)=>{const button=event.target.closest('[data-remove-field]');if(!button)return;draft=readDraft();draft.splice(Number(button.dataset.removeField),1);draw();};
    $('field-builder').onchange=(event)=>{if(event.target.matches('[data-part="type"]'))event.target.closest('.field-editor').querySelector('[data-options-wrap]').classList.toggle('hidden',event.target.value!=='select');};
    $('activity-mode').onchange=()=>{if(!activity && $('activity-mode').value==='individual' && !readDraft().some((f)=>f.key==='serie')){draft=readDraft();draft.unshift({key:'serie',label:'Serie del medidor',type:'text',required:true});draw();}};
    $('activity-cancel').onclick=closeDialog;
    $('activity-form').onsubmit=(event)=>{event.preventDefault();busy(event.submitter,async()=>{const fields=readDraft();if(new Set(fields.map((f)=>f.key)).size!==fields.length)throw new Error('Cada dato debe tener un nombre diferente.');if(fields.some((f)=>!f.key || !f.label || f.type==='select'&&!f.options.length))throw new Error('Completa los nombres y las opciones de cada lista.');const payload={name:$('activity-name').value.trim(),mode:$('activity-mode').value,unit:$('activity-unit').value.trim(),active:$('activity-active').checked,fields};if(activity)payload.id=activity.id;await api('/api/actividades',payload);await loadReferences();closeDialog();toast(activity?'Nueva versión guardada. El histórico se conserva.':'Actividad creada. Puedes asignarla a los colaboradores.');await loadActivities();},$('activity-error'));};
  });
}

async function loadImport() { $('import-activity').querySelectorAll('option').forEach((option)=>{option.textContent=S.activities.find((a)=>a.id===option.value)?.name || option.textContent;});updateTemplateLinks(); }
function updateTemplateLinks() { ['xlsx','csv'].forEach((f)=>$(`template-${f}`).href=`/api/plantilla.${f}?activity_id=${encodeURIComponent($('import-activity').value)}`); S.preview=null;$('import-preview').classList.add('hidden'); }
async function fileBase64(file) { const bytes=new Uint8Array(await file.arrayBuffer());let binary='';for(let i=0;i<bytes.length;i+=32768)binary+=String.fromCharCode(...bytes.subarray(i,i+32768));return btoa(binary); }
async function previewImport() {
  const file=$('import-file').files[0];if(!file)throw new Error('Selecciona un archivo Excel o CSV.');if(file.size>8*1024*1024)throw new Error('Para esta versión, usa archivos de hasta 8 MB. Divide las cargas mayores.');
  S.preview=await api('/api/import/preview',{activity_id:$('import-activity').value,filename:file.name,content_base64:await fileBase64(file)});renderImportPreview();
}
function renderImportPreview() {
  const data=S.preview; const errors=data.errors || [],warnings=data.warnings || [];
  $('import-preview').classList.remove('hidden');
  $('import-preview').innerHTML=`<div class="card-heading"><div><h2>Resultado de la validación</h2><p>${fmt(data.rows_count)} filas leídas · ${fmt(data.valid_count)} válidas</p></div><span class="step-chip">02 · CONFIRMAR</span></div>${data.already_imported?'<div class="notice soft">Este archivo ya fue importado. Repetir la carga no añadirá registros.</div>':''}${errors.length?`<div class="notice error"><strong>${fmt(errors.length)} incidencias impiden confirmar la carga.</strong><p>Corrige el archivo y vuelve a revisarlo.</p></div>${table(['Fila','Error'],errors.map((e)=>[escapeHtml(e.row),escapeHtml(e.message)]))}`:'<div class="notice success">Las filas superaron la validación inicial.</div>'}${table(['Colaborador','Cantidad atribuida'],(data.summary || []).map((r)=>[escapeHtml(r.responsible_name),fmt(r.quantity)]),'No hay cantidades listas para confirmar.')}${warnings.length?`<div class="notice warning"><strong>Advertencias que requieren revisión</strong><ul>${warnings.slice(0,20).map((w)=>`<li>Fila ${escapeHtml(w.row)}: ${escapeHtml(w.message)}</li>`).join('')}</ul></div><label class="checkbox-label"><input id="import-confirm-warnings" type="checkbox"> He revisado las advertencias y confirmo los reingresos indicados.</label>`:''}<div class="dialog-actions"><button id="confirm-import" class="btn primary" ${errors.length || !data.valid_count || data.already_imported?'disabled':''}>Confirmar ${fmt(data.valid_count)} registros</button></div><div id="import-confirm-error" class="notice error hidden" role="alert"></div>`;
  $('confirm-import').onclick=()=>busy($('confirm-import'),confirmImport,$('import-confirm-error'));
}
async function confirmImport() {
  const warningCheckbox=$('import-confirm-warnings');if(warningCheckbox && !warningCheckbox.checked)throw new Error('Revisa y confirma las advertencias antes de continuar.');
  const data=await api('/api/import/confirm',{preview_id:S.preview.preview_id,confirm_reentry:warningCheckbox?.checked || false});
  $('confirm-import').disabled=true;S.preview.already_imported=true;
  $('import-preview').innerHTML=`<div class="notice success"><strong>${data.already_imported?'La carga ya estaba confirmada.':'Carga confirmada'}</strong><p>${fmt(data.imported)} registros incorporados. Se conservaron su responsable y el supervisor que realizó la carga.</p></div><button class="btn secondary" id="see-imported">Consultar registros →</button>`;
  $('see-imported').onclick=()=>navigate('records');toast('Importación finalizada.');
}
async function loadReceipts() {
  $('new-receipt').classList.toggle('hidden',!activeActivities().some((a)=>a.id==='recepcion'));
  const query=new URLSearchParams(filterQuery());query.delete('desde');query.delete('hasta');
  const data=await api(`/api/ordenes?${query}`);S.orders=data.orders || [];renderReceiptOrders();
}
function renderReceiptOrders() {
  const orders=S.orders || [],scope=$('receipts-state').value;
  $('receipts-metrics').innerHTML=metricCards([
    ['Órdenes en seguimiento',orders.length,'Órdenes dentro del alcance seleccionado'],
    ['Pendientes activos',orders.filter((o)=>o.state==='pendiente' || o.state==='por_confirmar').length,'Entregas aún por completar'],
    ['Alertas',orders.filter((o)=>o.signal==='rojo' && o.state!=='cerrada').length,'Vencimiento o recepción en exceso'],
    ['Lotes cerrados',orders.filter((o)=>o.state==='cerrada').length,'Con acta de cierre conservada']]);
  const visible=orders.filter((o)=>scope==='all' || scope==='active' && o.state!=='cerrada' || scope==='overdue' && o.signal==='rojo' && o.state!=='cerrada' || scope==='closed' && o.state==='cerrada' || scope==='complete' && o.state==='completa');
  $('receipts-table').innerHTML=table(['Proceso / orden','SAP','Recibido / esperado','Pendiente','Seguimiento','Entregas','Acciones'],visible.map((o)=>[
    `<strong class="mono">${escapeHtml(o.process)}</strong><small>${escapeHtml(o.order_number)}</small>`,escapeHtml(o.sap),`${fmt(o.received)} / ${o.expected===null?'Por confirmar':fmt(o.expected)}${o.own_received===undefined?'':`<small>Tu aporte: ${fmt(o.own_received)}</small>`}`,
    o.pending===null?'Por confirmar':`${fmt(o.pending)}${o.excess?`<small class="danger-text">Exceso: ${fmt(o.excess)}</small>`:''}`,
    `${signalBadge(o.signal,orderStateLabel(o))}${o.due_date?`<small>Fecha límite: ${escapeHtml(prettyDate(o.due_date))}</small>`:''}`,fmt(o.deliveries),
    `<button class="mini-button" data-order-detail="${o.id}">Ver detalle</button>${isManager() && o.state!=='cerrada'?`<button class="mini-button" data-order-edit="${o.id}">Editar orden</button>`:''}${o.state!=='cerrada' && activeActivities().some((a)=>a.id==='recepcion')?`<button class="mini-button" data-order-delivery="${o.id}">＋ Entrega</button>`:''}${isManager() && o.state==='completa' && !o.process_conflict && !o.excess?`<button class="mini-button" data-order-close="${o.id}">Cerrar lote</button>`:''}${isManager() && o.state==='cerrada'?`<button class="mini-button" data-order-reopen="${o.id}">Reabrir</button>`:''}`]),'No hay órdenes para este estado. Puedes crear una orden o registrar la primera entrega.');
}
function orderStateLabel(order) {return order.state==='cerrada'?'Cerrada':order.process_conflict?'Proceso duplicado: revisar':order.excess?'Exceso recibido':order.overdue?'Vencida':({completa:'Completa, lista para cerrar',pendiente:'Pendiente',por_confirmar:'Cantidad por confirmar'}[order.state] || order.state);}
function createOrder() {
  openDialog('Crear orden de recepción',`<form id="order-form" class="dialog-form"><div class="form-grid two"><label>Número de proceso único<input id="order-process" required maxlength="120" autocomplete="off"></label><label>Número de orden<input id="order-number" required maxlength="120"></label><label>Código SAP<input id="order-sap" required maxlength="60" list="sap-list"></label><label>Cantidad esperada<input id="order-expected" type="number" required min="1" max="1000000" step="1"></label><label>Fecha límite<input id="order-due" type="date"></label><label>Observaciones<textarea id="order-notes" maxlength="1500" rows="2"></textarea></label></div><div id="order-error" class="notice error hidden" role="alert"></div><div class="dialog-actions"><button id="order-cancel" type="button" class="btn secondary">Cancelar</button><button type="submit" class="btn primary">Crear orden</button></div></form>`,()=>{
    $('order-cancel').onclick=closeDialog;$('order-form').onsubmit=(event)=>{event.preventDefault();busy(event.submitter,async()=>{await api('/api/ordenes',{process:$('order-process').value.trim(),order_number:$('order-number').value.trim(),sap:$('order-sap').value.trim(),expected:Number($('order-expected').value),due_date:$('order-due').value,notes:$('order-notes').value.trim()});closeDialog();toast('Orden creada. Cada entrega conservará su trazabilidad.');await loadReceipts();},$('order-error'));};
  });
}
function editOrder(id) {
  const order=(S.orders || []).find((o)=>String(o.id)===String(id));if(!order)return;
  openDialog('Actualizar seguimiento de la orden',`<form id="order-edit-form" class="dialog-form"><p class="muted">Orden ${escapeHtml(order.order_number)} · SAP ${escapeHtml(order.sap)}. Las entregas y sus responsables se conservan.</p><div class="form-grid two"><label>Número de proceso único<input id="order-edit-process" required maxlength="160" value="${escapeHtml(order.process)}"></label><label>Cantidad esperada<input id="order-edit-expected" type="number" min="0" max="1000000" step="1" value="${order.expected===null?'':order.expected}"></label><label>Fecha límite<input id="order-edit-due" type="date" value="${escapeHtml(order.due_date || '')}"></label><label>Observaciones<textarea id="order-edit-notes" rows="2" maxlength="1500">${escapeHtml(order.notes || '')}</textarea></label></div><label>Motivo del cambio<textarea id="order-edit-reason" required minlength="3" maxlength="1500" rows="2"></textarea></label><div id="order-edit-error" class="notice error hidden" role="alert"></div><div class="dialog-actions"><button id="order-edit-cancel" class="btn secondary" type="button">Cancelar</button><button class="btn primary" type="submit">Guardar seguimiento</button></div></form>`,()=>{
    $('order-edit-cancel').onclick=closeDialog;$('order-edit-form').onsubmit=(event)=>{event.preventDefault();busy(event.submitter,async()=>{await api('/api/ordenes',{id:order.id,process:$('order-edit-process').value.trim(),expected:$('order-edit-expected').value===''?null:Number($('order-edit-expected').value),due_date:$('order-edit-due').value,notes:$('order-edit-notes').value.trim(),reason:$('order-edit-reason').value.trim()});closeDialog();toast('Seguimiento actualizado con su motivo en auditoría.');await loadReceipts();},$('order-edit-error'));};
  });
}
async function showOrderDetail(id) {
  const data=await api(`/api/ordenes/${id}`),order=data.order;
  openDialog(`Proceso ${order.process}`,`<div class="detail-title">${signalBadge(order.signal,orderStateLabel(order))}</div><dl class="detail-list"><dt>Orden</dt><dd>${escapeHtml(order.order_number)}</dd><dt>Código SAP</dt><dd>${escapeHtml(order.sap)}</dd><dt>Recibido / esperado</dt><dd>${fmt(order.received)} / ${order.expected===null?'Por confirmar':fmt(order.expected)}</dd><dt>Pendiente</dt><dd>${order.pending===null?'Por confirmar':fmt(order.pending)}</dd><dt>Fecha límite</dt><dd>${escapeHtml(prettyDate(order.due_date))}</dd><dt>Observaciones</dt><dd>${escapeHtml(order.notes || '—')}</dd></dl><h3>Entregas registradas</h3>${table(['Fecha','Cantidad','Responsable','Registrado por','Estado'],(data.deliveries || []).map((r)=>[escapeHtml(prettyDate(r.work_date)),fmt(r.quantity),escapeHtml(r.responsible_name || '—'),escapeHtml(r.recorded_by_name || '—'),badge(r.state==='anulado'?'Anulada':'Válida',r.state==='anulado'?'danger':'good')]),'La primera entrega aparecerá aquí.')}${data.certificates?.length?`<h3>Actas de cierre conservadas</h3>${table(['Acta / fecha','Estado','Huella SHA-256','Descargas'],data.certificates.map((c)=>[`${escapeHtml(c.number)}<small>${escapeHtml(prettyTime(c.created_at))}</small>`,badge(c.current?'Vigente':'Histórica',c.current?'good':'muted'),`<span class="hash-value">${escapeHtml(c.hash)}</span>`,`<a class="btn small secondary" href="/api/ordenes/${order.id}/acta.pdf?certificate_id=${encodeURIComponent(c.id)}">PDF</a> <a class="btn small secondary" href="/api/ordenes/${order.id}/acta.json?certificate_id=${encodeURIComponent(c.id)}">JSON</a>`]))}`:''}<div class="dialog-actions">${order.state==='cerrada'?`<a href="/api/ordenes/${order.id}/acta.pdf" class="btn primary">Descargar acta PDF</a><button class="btn secondary" data-order-certificate="${order.id}">Ver sello del acta</button>`:`${activeActivities().some((a)=>a.id==='recepcion')?`<button class="btn secondary" data-order-delivery="${order.id}">Registrar entrega</button>`:''}${isManager() && order.state==='completa' && !order.process_conflict && !order.excess?`<button class="btn primary" data-order-close="${order.id}">Cerrar lote</button>`:''}`}</div>`);
}
async function registerOrderDelivery(id) {
  const order=(S.orders || []).find((o)=>String(o.id)===String(id)) || (await api(`/api/ordenes/${id}`)).order;
  closeDialog();await navigate('capture');$('capture-activity').value='recepcion';renderCaptureFields();
  for(const [key,value] of Object.entries({numero_orden:order.order_number,proceso:order.process,sap:order.sap,cantidad_esperada:order.expected ?? ''}))setFieldValue($(`capture-field-${key}`),value);
  $('capture-quantity').value=String(order.pending>0?order.pending:1);updateSapHint(true);$('capture-quantity').focus();
}
function changeOrderState(id,reopen=false) {
  openDialog(reopen?'Reabrir lote':'Cerrar y certificar lote',`<form id="order-state-form" class="dialog-form"><p>${reopen?'Se conservará el acta anterior y quedará registrado el motivo de reapertura.':'El sistema comprobará que lo recibido coincide con lo esperado y conservará un acta con su huella SHA-256.'}</p><label>Motivo<textarea id="order-state-reason" rows="3" maxlength="1500" ${reopen?'required minlength="3"':''}></textarea></label><div id="order-state-error" class="notice error hidden" role="alert"></div><div class="dialog-actions"><button id="order-state-cancel" type="button" class="btn secondary">Cancelar</button><button class="btn primary" type="submit">${reopen?'Reabrir lote':'Cerrar y generar acta'}</button></div></form>`,()=>{
    $('order-state-cancel').onclick=closeDialog;$('order-state-form').onsubmit=(event)=>{event.preventDefault();busy(event.submitter,async()=>{await api(`/api/ordenes/${id}/${reopen?'reabrir':'cerrar'}`,{reason:$('order-state-reason').value.trim()});closeDialog();toast(reopen?'Lote reabierto con trazabilidad.':'Lote cerrado; el acta está disponible.');await loadReceipts();await showOrderDetail(id);},$('order-state-error'));};
  });
}
async function showOrderCertificate(id) {
  const data=await api(`/api/ordenes/${id}/acta`),certificate=data.certificate;
  openDialog('Sello del acta de cierre',`<dl class="detail-list"><dt>Acta</dt><dd>${escapeHtml(certificate.number)}</dd><dt>Emitida</dt><dd>${escapeHtml(prettyTime(certificate.created_at))}</dd><dt>Huella SHA-256</dt><dd class="hash-value">${escapeHtml(certificate.hash)}</dd></dl><p class="muted">La huella corresponde a los datos conservados al cerrar el lote. No equivale a una firma digital institucional.</p><a href="/api/ordenes/${id}/acta.pdf" class="btn primary">Descargar acta PDF</a>`);
}
function renderGoals(goals, compact=false) { const list=compact?goals.slice(0,5):goals;return table(['Colaborador','Actividad','Período','Producción / meta','Avance','Estado'],list.map((g)=>[escapeHtml(g.responsible_name || 'Equipo'),`<strong>${escapeHtml(g.activity_name)}</strong><small>${escapeHtml(g.unit)}</small>`,`${escapeHtml(prettyDate(g.start_date))}<small>${escapeHtml(prettyDate(g.end_date))}</small>`,`${fmt(g.produced)} / ${fmt(g.target)}`,progress(g.pct),badge(String(g.state || '').replaceAll('_',' '),g.pct>=100?'good':g.state==='vencida'?'danger':'soft')]),'Las metas aparecerán cuando el supervisor las asigne.'); }
async function loadGoals() { const data=await api('/api/metas');$('goals-table').innerHTML=renderGoals(data.goals || []);$('goals-hint').textContent=isManager()?'Cada avance corresponde a una actividad y unidad.':'Aquí encontrarás las metas asignadas a tu cuenta.';if(!$('goal-from').value)$('goal-from').value=today();if(!$('goal-to').value)$('goal-to').value=today();updateGoalUnit(); }
function updateGoalUnit() {let wrap=$('goal-unit-wrap');if(!wrap){wrap=document.createElement('label');wrap.id='goal-unit-wrap';wrap.innerHTML='Unidad<select id="goal-unit"><option value="medidores">Medidores</option><option value="sellos">Sellos</option></select>';$('goal-form').querySelector('.form-grid').insertBefore(wrap,$('goal-form').querySelector('.field-action'));}wrap.classList.toggle('hidden',$('goal-activity').value!=='asignacion');}

async function loadUsers() { const data=await api('/api/usuarios');S.users=data.users || []; $('users-table').innerHTML=table(['Colaborador','Usuario','Perfil','Actividades','Estado','Acciones'],S.users.map((u)=>[`<strong>${escapeHtml(u.name)}</strong>`,escapeHtml(u.username),escapeHtml(roleNames[u.role] || u.role),escapeHtml((u.activity_ids || []).map((id)=>S.activities.find((a)=>a.id===id)?.name || id).join(' · ') || 'Sin actividades'),badge(u.active?'Activo':'Inactivo',u.active?'good':'muted'),`${S.user.role==='administrador' || u.role==='tecnico'?`<button class="mini-button" data-edit-user="${u.id}">Editar</button>`:''}${u.role==='tecnico'?`<button class="mini-button" data-reset-user="${u.id}">Restablecer acceso</button>`:''}`])); }
function editUser(user=null) {
  const roles=S.user.role==='administrador'?['tecnico','supervisor','administrador','visitante']:['tecnico'];
  openDialog(user?'Editar colaborador':'Agregar colaborador',`<form id="user-form" class="dialog-form"><div class="form-grid two"><label>Nombre completo<input id="user-name" required maxlength="90" value="${escapeHtml(user?.name || '')}"></label><label>Usuario / código de empleado<input id="user-username" required maxlength="35" value="${escapeHtml(user?.username || '')}" ${user?'readonly':''} autocomplete="off"></label></div>${user?`<p>Perfil: <strong>${escapeHtml(roleNames[user.role] || user.role)}</strong></p>`:`<label>Perfil<select id="user-role">${options(roles.map((r)=>({value:r,label:roleNames[r]})),'tecnico',null)}</select></label><div id="user-password-wrap" class="hidden"><label>Contraseña inicial propia<input id="user-password" type="password" minlength="10" maxlength="128" autocomplete="new-password"></label></div><div id="user-code-hint" class="notice soft">Para colaboradores, la primera contraseña será su mismo código de empleado. El cambio posterior es opcional.</div>`}<label class="checkbox-label"><input id="user-active" type="checkbox" ${user?.active===false?'':'checked'} ${user?.id===S.user.id?'disabled':''}> Cuenta activa</label><fieldset><legend>Actividades habilitadas</legend><p class="muted small-text">La persona podrá cambiar entre estas actividades y fijar una durante la jornada.</p><div class="user-activity-checks">${S.activities.filter((a)=>a.active).map((a)=>`<label class="checkbox-label"><input type="checkbox" data-user-activity="${escapeHtml(a.id)}" ${(user?.activity_ids || []).includes(a.id)?'checked':''}>${escapeHtml(a.name)}</label>`).join('')}</div><button type="button" id="select-all-activities" class="text-button">Seleccionar todas</button></fieldset><div id="user-error" class="notice error hidden" role="alert"></div><div class="dialog-actions"><button id="user-cancel" type="button" class="btn secondary">Cancelar</button><button type="submit" class="btn primary">${user?'Guardar cambios':'Crear acceso'}</button></div></form>`,()=>{
    $('user-cancel').onclick=closeDialog;$('select-all-activities').onclick=()=>document.querySelectorAll('[data-user-activity]').forEach((n)=>n.checked=true);
    if($('user-role'))$('user-role').onchange=()=>{const nontech=$('user-role').value!=='tecnico';$('user-password-wrap').classList.toggle('hidden',!nontech);$('user-password').required=nontech;$('user-code-hint').classList.toggle('hidden',nontech);};
    $('user-form').onsubmit=(event)=>{event.preventDefault();busy(event.submitter,async()=>{const assigned=[...document.querySelectorAll('[data-user-activity]:checked')].map((n)=>n.dataset.userActivity);const payload={name:$('user-name').value.trim(),active:$('user-active').checked,activity_ids:assigned};if(user)await api(`/api/usuarios/${user.id}/actualizar`,payload);else {payload.username=$('user-username').value.trim();payload.role=$('user-role').value;if(payload.role!=='tecnico')payload.password=$('user-password').value;await api('/api/usuarios',payload);}await loadReferences();closeDialog();toast(user?'Colaborador actualizado.':'Acceso creado.');await loadUsers();},$('user-error'));};
  });
}
async function loadCatalogs() {
  renderCatalogValues();const configs=S.sap.flatMap((item)=>(item.configurations?.length?item.configurations:[{...item,id:''}]).map((config)=>({...config,code:item.code,code_active:item.active})));
  $('sap-table').innerHTML=table(['SAP / configuración','Voltaje','Clasificación','Marca / modelo','Estado','Acción'],configs.map((c)=>[`${escapeHtml(c.code)}<small>${escapeHtml(c.label || 'Principal')}</small>`,escapeHtml(c.voltage || '—'),escapeHtml(c.classification || '—'),`${escapeHtml(c.brand || 'Independiente')}<small>${escapeHtml(c.model || '')}</small>`,badge(c.active && c.code_active?'Activa':'Inactiva',c.active && c.code_active?'good':'muted'),`<button class="mini-button" data-edit-sap="${escapeHtml(c.code)}" data-sap-config="${escapeHtml(c.id)}">Editar</button>`]));
}
function selectSapConfiguration(code,configurationId=null) {
  const item=S.sap.find((c)=>c.code===code),select=$('sap-configuration');
  const previous=configurationId!==null?String(configurationId):select.value;
  select.innerHTML=options([{value:'',label:'Configuración principal'},...(item?.configurations || []).map((c)=>({value:c.id,label:[c.label,c.voltage,c.classification].filter(Boolean).join(' · ')})),{value:'new',label:'＋ Nueva configuración'}],previous,null);
  const config=previous==='new'?null:(item?.configurations || []).find((c)=>String(c.id)===previous) || (previous===''?item:null);
  if(config){$('sap-voltage').value=config.voltage || '';$('sap-classification').value=config.classification || '';$('sap-brand').value=config.brand || '';$('sap-model').value=config.model || '';$('sap-label').value=config.label || '';$('sap-active').checked=Boolean(config.active);}
  else if(previous==='new'){for(const id of ['sap-voltage','sap-classification','sap-brand','sap-model','sap-label'])$(id).value='';$('sap-active').checked=true;}
}
function renderCatalogValues() { const kind=$('catalog-kind').value; $('catalog-values').innerHTML=(S.catalog[kind] || []).map((v)=>`<span class="field-pill">${escapeHtml(v)}</span>`).join(''); }
async function loadAudit() {
  const [data,integrity]=await Promise.all([api('/api/auditoria'),api('/api/auditoria/integridad')]);S.audit=data.entries || [];
  $('audit-integrity').className=`notice ${integrity.ok?'success':'error'}`;$('audit-integrity').innerHTML=`${signalBadge(integrity.ok?'verde':'rojo',integrity.ok?'Cadena de auditoría íntegra':'Revisar integridad de auditoría')}<p>${fmt(integrity.entries)} entradas verificadas. Las entradas de auditoría no admiten edición ni eliminación.${integrity.invalid_id?` Primera incidencia: ${escapeHtml(integrity.invalid_id)}.`:''}</p><small class="hash-value">Huella: ${escapeHtml(integrity.head_hash || 'Sin entradas')}</small>`;
  $('audit-table').innerHTML=table(['Fecha','Persona','Operación','Referencia','Motivo','Detalle'],S.audit.map((a)=>[escapeHtml(prettyTime(a.created_at)),escapeHtml(a.actor_name || 'Sistema'),escapeHtml(a.action),`${escapeHtml(a.entity)} #${escapeHtml(a.entity_id)}`,escapeHtml(a.reason || '—'),`<button class="mini-button" data-audit="${a.id}">Ver cambio</button>`]));
}
function auditValues(value) { if(!value || typeof value!=='object')return `<p class="muted">${escapeHtml(value ?? 'Sin datos anteriores')}</p>`;const entries=Object.entries(value).filter(([key])=>!/password|hash|salt|csrf|token/i.test(key));return `<dl class="detail-list">${entries.map(([key,val])=>`<dt>${escapeHtml(labels[key] || key)}</dt><dd>${val && typeof val==='object'?Array.isArray(val)?escapeHtml(val.map((x)=>typeof x==='object'?(x.label || x.name || 'Elemento'):x).join(', ')):auditValues(val):escapeHtml(val===true?'Sí':val===false?'No':val ?? '—')}</dd>`).join('')}</dl>`; }
async function loadAccount() {
  const sharedPublicAccess=S.publicDemo && ['visitante_demo','90001','90002'].includes(S.user.username);
  $('password-form').classList.toggle('hidden',sharedPublicAccess);
  $('shared-demo-account-notice').classList.toggle('hidden',!sharedPublicAccess);
  $('profile-details').innerHTML=`<dt>Nombre</dt><dd>${escapeHtml(S.user.name)}</dd><dt>Usuario</dt><dd>${escapeHtml(S.user.username)}</dd><dt>Perfil</dt><dd>${escapeHtml(roleNames[S.user.role])}</dd><dt>Estado</dt><dd>${badge('Activo','good')}</dd>`;
  $('password-hint').textContent=S.user.must_change?'Para continuar, sustituye la contraseña provisional por una propia.':S.user.role==='tecnico'?'Puedes cambiarla si lo deseas. Si la olvidas, tu supervisor puede restablecerla.':'Elige una contraseña propia, distinta de tu código, con al menos 10 caracteres.';
  $('password-new').minLength=S.user.role==='tecnico'?4:10;
}

function bindEvents() {
  let resizeTimer;window.addEventListener('resize',()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>{if(!S.user)return;if(S.view==='comparison' && S.comparison)comparisonChart(S.comparison);else if(['dashboard','quality'].includes(S.view)){const keys=S.view==='dashboard'?['activity','day','voltage','collaborator']:['quality-results','quality-failures'];for(const key of keys){const chart=S.charts[key];if(chart)svgChart(`chart-${key}`,chart.data,chart.title,chart.unit);}}},180);});
  document.addEventListener('click',(event)=>{
    const view=event.target.closest('[data-view]');if(view)navigate(view.dataset.view);
    const chart=event.target.closest('[data-export-chart]');if(chart)exportChart(chart.dataset.exportChart,chart.dataset.format,chart);
    const activity=event.target.closest('[data-edit-activity]');if(activity)editActivity(S.activities.find((a)=>a.id===activity.dataset.editActivity));
    const edit=event.target.closest('[data-edit-user]');if(edit)editUser(S.users.find((u)=>String(u.id)===edit.dataset.editUser));
    const reset=event.target.closest('[data-reset-user]');if(reset){const user=S.users.find((u)=>String(u.id)===reset.dataset.resetUser);confirmDialog('Restablecer acceso',`${user.name} volverá a acceder con su código como usuario y contraseña. Sus sesiones se cerrarán y su historial se conservará.`,async()=>{await api(`/api/usuarios/${user.id}/restablecer`,{});toast('Acceso restablecido al código de empleado.');},'Restablecer acceso');}
    const rec=event.target.closest('[data-event]');if(rec){const r=S.records.find((x)=>String(x.id)===rec.dataset.event);if(!r)return;if(rec.dataset.action==='detail')openDialog('Detalle del registro',detailHtml(r));if(rec.dataset.action==='edit')editRecord(r);if(rec.dataset.action==='void')changeRecordState(r,false);if(rec.dataset.action==='restore')changeRecordState(r,true);}
    const audit=event.target.closest('[data-audit]');if(audit){const a=S.audit.find((x)=>String(x.id)===audit.dataset.audit);if(a)openDialog('Detalle del cambio',`<p>${escapeHtml(a.actor_name || 'Sistema')} · ${escapeHtml(prettyTime(a.created_at))}</p><p>${escapeHtml(a.reason || '')}</p><h3>Antes</h3>${auditValues(a.before)}<h3>Después</h3>${auditValues(a.after)}`);}
    const sapEdit=event.target.closest('[data-edit-sap]');if(sapEdit){$('sap-code').value=sapEdit.dataset.editSap;selectSapConfiguration(sapEdit.dataset.editSap,sapEdit.dataset.sapConfig);$('sap-code').focus();}
    const orderEdit=event.target.closest('[data-order-edit]');if(orderEdit)editOrder(orderEdit.dataset.orderEdit);
    const orderDetail=event.target.closest('[data-order-detail]');if(orderDetail)busy(orderDetail,()=>showOrderDetail(orderDetail.dataset.orderDetail));
    const orderDelivery=event.target.closest('[data-order-delivery]');if(orderDelivery)busy(orderDelivery,()=>registerOrderDelivery(orderDelivery.dataset.orderDelivery));
    const orderClose=event.target.closest('[data-order-close]');if(orderClose)changeOrderState(orderClose.dataset.orderClose,false);
    const orderReopen=event.target.closest('[data-order-reopen]');if(orderReopen)changeOrderState(orderReopen.dataset.orderReopen,true);
    const orderCertificate=event.target.closest('[data-order-certificate]');if(orderCertificate)busy(orderCertificate,()=>showOrderCertificate(orderCertificate.dataset.orderCertificate));
  });
  $('auth-form').onsubmit=(event)=>{event.preventDefault();busy($('auth-submit'),async()=>{const credentials={username:$('auth-username').value.trim(),password:$('auth-password').value};if(S.setup){await api('/api/setup',{...credentials,name:$('auth-name').value.trim()});S.setup=false;}await api('/api/login',credentials);$('auth-password').value='';await enterApp(await api('/api/me'));},$('auth-error'));};
  $('logout-button').onclick=()=>busy($('logout-button'),async()=>{await api('/api/logout',{});S.user=null;S.csrf='';$('password-form').reset();showAuth(false);});
  $('menu-toggle').onclick=()=>setMenu(!document.body.classList.contains('menu-open'));$('sidebar-backdrop').onclick=()=>setMenu(false);$('account-shortcut').onclick=()=>navigate('account');$('quick-capture').onclick=()=>navigate('capture');
  $('dialog-close').onclick=closeDialog;$('app-dialog').addEventListener('click',(e)=>{if(e.target===$('app-dialog')){const r=$('app-dialog').getBoundingClientRect();if(e.clientX<r.left || e.clientX>r.right || e.clientY<r.top || e.clientY>r.bottom)closeDialog();}});
  $('toggle-filters').onclick=()=>{const collapsed=$('global-filters').classList.toggle('filter-collapsed');$('toggle-filters').setAttribute('aria-expanded',String(!collapsed));};
  $('filter-form').onsubmit=(event)=>{event.preventDefault();if(!['comparison','receipts'].includes(S.view) && $('filter-from').value && $('filter-to').value && $('filter-from').value>$('filter-to').value)return toast('La fecha inicial debe ser anterior a la final.','warning');S.page=1;navigate(S.view);};
  $('clear-filters').onclick=()=>{$('filter-form').reset();S.page=1;navigate(S.view);};
  $('capture-activity').onchange=()=>{renderCaptureFields();storePin();};$('pin-activity').onchange=storePin;
  $('capture-form').onsubmit=(event)=>{event.preventDefault();busy($('capture-submit'),()=>saveCapture(),$('capture-error'));};
  $('records-search').onclick=()=>{S.page=1;busy($('records-search'),loadRecords);};$('records-prev').onclick=()=>{if(S.page>1){S.page--;busy(null,loadRecords);}};$('records-next').onclick=()=>{if(S.page<S.pages){S.page++;busy(null,loadRecords);}};
  $('history-form').onsubmit=(event)=>{event.preventDefault();busy(event.submitter,searchHistory);};$('new-activity').onclick=()=>editActivity();$('new-user').onclick=()=>editUser();
  $('create-backup').onclick=()=>busy($('create-backup'),async()=>{const result=await api('/api/backup',{});toast(`Respaldo creado. ${result.message || 'Se guardó en la carpeta de respaldos de esta instalación.'}`);});
  $('import-activity').onchange=updateTemplateLinks;$('import-file').onchange=()=>{S.preview=null;$('import-preview').classList.add('hidden');};$('import-form').onsubmit=(event)=>{event.preventDefault();busy(event.submitter,previewImport,$('import-error'));};
  $('create-order').onclick=createOrder;$('receipts-state').onchange=renderReceiptOrders;
  $('quality-form').onsubmit=(event)=>{event.preventDefault();busy(event.submitter,loadQuality);};
  $('comparison-form').onsubmit=(event)=>{event.preventDefault();busy(event.submitter,loadComparison,$('comparison-error'));};
  $('new-receipt').onclick=async()=>{await navigate('capture');$('capture-activity').value='recepcion';renderCaptureFields();};
  $('goal-activity').onchange=updateGoalUnit;$('goal-form').onsubmit=(event)=>{event.preventDefault();busy(event.submitter,async()=>{const payload={responsible_id:Number($('goal-responsible').value),activity_id:$('goal-activity').value,start_date:$('goal-from').value,end_date:$('goal-to').value,target:Number($('goal-target').value)};if(payload.activity_id==='asignacion')payload.unit=$('goal-unit').value;await api('/api/metas',payload);toast('Meta asignada.');$('goal-target').value='';await loadGoals();});};
  $('sap-code').onchange=()=>selectSapConfiguration($('sap-code').value.trim(),'');$('sap-configuration').onchange=()=>selectSapConfiguration($('sap-code').value.trim());
  $('sap-clear').onclick=()=>{$('sap-form').reset();selectSapConfiguration('','');};
  $('sap-form').onsubmit=(event)=>{event.preventDefault();busy(event.submitter,async()=>{const payload={code:$('sap-code').value.trim(),voltage:$('sap-voltage').value.trim(),classification:$('sap-classification').value.trim(),brand:$('sap-brand').value.trim(),model:$('sap-model').value.trim(),label:$('sap-label').value.trim(),active:$('sap-active').checked};if($('sap-configuration').value)payload.configuration_id=$('sap-configuration').value;await api('/api/sap',payload);await loadReferences();await loadCatalogs();toast('Configuración SAP guardada. El histórico se conserva.');},$('page-error'));};
  $('catalog-kind').onchange=renderCatalogValues;$('catalog-form').onsubmit=(event)=>{event.preventDefault();busy(event.submitter,async()=>{await api('/api/catalogos',{kind:$('catalog-kind').value,label:$('catalog-label').value.trim()});$('catalog-label').value='';await loadReferences();await loadCatalogs();toast('Opción agregada al catálogo.');});};
  $('password-form').onsubmit=(event)=>{event.preventDefault();busy(event.submitter,async()=>{if($('password-new').value!==$('password-confirm').value)throw new Error('Las contraseñas nuevas no coinciden.');const data=await api('/api/password',{current_password:$('password-current').value,password:$('password-new').value});$('password-form').reset();if(data.relogin){S.user=null;S.csrf='';showAuth(false);toast('Contraseña actualizada. Entra de nuevo con tu nueva clave.');}else toast('Contraseña actualizada.');});};
}
async function init() {
  bindEvents();const day=today();$('filter-from').value=`${day.slice(0,7)}-01`;$('filter-to').value=day;$('capture-date').value=day;
  setComparisonDefaults();
  if(window.matchMedia('(max-width:760px)').matches){$('global-filters').classList.add('filter-collapsed');$('toggle-filters').setAttribute('aria-expanded','false');}
  try {const me=await api('/api/me');S.demo=Boolean(me.demo);S.publicDemo=Boolean(me.public_demo);S.setup=Boolean(me.setup_required);if(me.logged)await enterApp(me);else showAuth();}
  catch(error){showAuth(false);showError($('auth-error'),error);}
}
init();
