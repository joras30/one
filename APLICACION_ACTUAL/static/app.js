'use strict';

const $ = (id) => document.getElementById(id);
const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = (value) => new Intl.NumberFormat('es-DO', {maximumFractionDigits: 2}).format(Number(value) || 0);
const today = () => new Intl.DateTimeFormat('en-CA', {timeZone: 'America/Santo_Domingo',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
const prettyDate = (value) => value ? new Intl.DateTimeFormat('es-DO',{dateStyle:'medium',timeZone:'America/Santo_Domingo'}).format(new Date(String(value).length === 10 ? `${value}T12:00:00-04:00` : value)) : '—';
const prettyTime = (value) => value ? new Intl.DateTimeFormat('es-DO',{dateStyle:'short',timeStyle:'short',timeZone:'America/Santo_Domingo'}).format(new Date(value)) : '—';
const newOperation = () => window.crypto?.randomUUID ? crypto.randomUUID() : `op-${Date.now()}-${Math.random().toString(36).slice(2)}`;
const roleNames = {tecnico:'Técnico',supervisor:'Supervisor',administrador:'Administrador',visitante:'Visitante'};
const modeNames = {lote:'Por cantidad',individual:'Por medidor',recepcion:'Recepción parcial'};
const S = {user:null,csrf:'',demo:false,publicDemo:false,setup:false,view:'dashboard',activities:[],users:[],catalog:{marcas:[],voltajes:[],condiciones:[]},sap:[],page:1,pages:1,records:[],preview:null,operation:newOperation(),charts:{},navigation:0};
const isManager = () => ['supervisor','administrador'].includes(S.user?.role);
const isVisitor = () => S.user?.role === 'visitante';
const activeActivities = () => S.activities.filter((a) => a.active && (isManager() || a.assigned !== false));
const personOptions = () => S.users.filter((u) => u.active && u.role !== 'visitante');
const labels = {serie:'Serie',sap:'Código SAP',marca:'Marca',modelo:'Modelo',sap_config_id:'Configuración SAP',tipo_inspeccion:'Tipo de inspección',fallo:'Fallo detectado',valor_referencia:'Valor de referencia',valor_medido:'Valor medido',tolerancia_pct:'Tolerancia (%)',desviacion_pct:'Desviación (%)',fuera_tolerancia:'Fuera de tolerancia',voltaje:'Voltaje',condicion:'Condición técnica',clasificacion:'Nuevo / recuperado',resultado:'Resultado de revisión',tiempo_minutos:'Tiempo del lote (min)',condicion_visual:'Condición visual',tipo_configuracion:'Tipo de configuración',destino:'Destinatario / destino',tipo_articulo:'Tipo de artículo',numero_orden:'Número de orden',proceso:'Proceso de recepción',cantidad_esperada:'Cantidad esperada',observaciones:'Observaciones',work_date:'Fecha de trabajo',responsible_id:'Responsable',quantity:'Cantidad',state:'Estado',name:'Nombre',active:'Activo',role:'Perfil',activity_ids:'Actividades asignadas'};
const pages = {
  operation:['REGISTRO','Registro de actividades del laboratorio','Registra actividades con validaciones y trazabilidad.'],
  bulk:['CARGA MASIVA','Plantillas y validación','Revisa todas las filas antes de guardar.'],
  assignments:['ASIGNACIONES','Actividades y permisos','Asignaciones vigentes para técnicos del laboratorio.'],
  scrap:['BAJAS','Bajas y piezas recuperadas','Propuestas, autorizaciones e historial permanente.'],
  master:['CONFIGURACIÓN','Catálogo maestro','Listas y artículos oficiales de la instalación.'],
  sapload:['SAP','Recuperados cargados a SAP','Resumen verificable desde los registros de sellado.'],
  dashboard:['PANORAMA GENERAL','Resumen de producción','Una vista clara del trabajo y los resultados del laboratorio.'],
  quality:['CONTROL DE CALIDAD','Inspección y calibración','Resultados técnicos, fallos y desviaciones con criterios visibles.'],
  comparison:['ANALÍTICA','Comparar períodos','Mide la variación entre períodos conservando cada actividad y unidad.'],
  capture:['OPERACIÓN DIARIA','Registrar actividad','Captura lo realizado; cada actividad pide sus propios datos.'],
  records:['PRODUCCIÓN','Registros del laboratorio','Consulta, filtra y descarga el detalle de la actividad.'],
  history:['TRAZABILIDAD','Consultar medidor','Cada revisión conserva su fecha, resultado y responsable.'],
  activities:['CONFIGURACIÓN','Actividades del laboratorio','Formularios que evolucionan conservando lo registrado.'],
  import:['CARGA SUPERVISADA','Importar Excel o CSV','Revisa la información antes de incorporarla a la producción.'],
  receipts:['SEGUIMIENTO','Recepciones y pendientes','Cada entrega suma al lote y conserva su detalle.'],
  goals:['PLANIFICACIÓN','Metas de producción','Objetivos claros por técnico, actividad y período.'],
  users:['EQUIPO','Personal y accesos','Personas, actividades habilitadas y acceso sencillo.'],
  catalogs:['CATÁLOGOS','SAP, marcas y condiciones','Listas actualizables para mantener una captura consistente.'],
  audit:['CONTROL','Historial de cambios','Correcciones y anulaciones con su motivo y responsable.'],
  labstats:['ESTADÍSTICAS','Estadísticas del laboratorio','Producción, movimientos y resultados con datos verificables.'],sealed:['SELLADO','MEDIDORES SELLADOS EN EL LABORATORIO','Importación oficial y análisis del sellado.'],sapmoves:['MOVIMIENTOS SAP','MEDIDORES RECUPERADOS CARGADOS EN SAP','Movimientos por artículo y almacén; sin producción individual.'],account:['MI CUENTA','Perfil y contraseña','Gestiona tu acceso al sistema.']
};

class ApiError extends Error { constructor(message, status, payload) { super(message); this.status = status; this.payload = payload; } }
async function api(path, payload) {
  const requestOwner=S.user?.id;
  const headers = {'Accept':'application/json'};
  if (payload !== undefined) { headers['Content-Type']='application/json'; if (S.csrf) headers['X-CSRF-Token']=S.csrf; }
  let response;
  try { response = await fetch(path, {method:payload === undefined ? 'GET':'POST',headers,credentials:'same-origin',body:payload === undefined ? undefined:JSON.stringify(payload)}); }
  catch (_) { throw new ApiError('No se pudo conectar. Comprueba que la aplicación siga abierta.',0,{}); }
  let data;
  try { data = await response.json(); } catch (_) { throw new ApiError('La aplicación devolvió una respuesta inesperada. Intenta de nuevo.',response.status,{}); }
  if (!response.ok) {
    if (response.status === 401 && S.user && S.user.id===requestOwner && !path.endsWith('/password')) { S.user=null; S.csrf=''; showAuth(false); }
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
  $('auth-help').textContent=setup?'La contraseña de administración debe tener al menos 10 caracteres y ser distinta del usuario.':S.publicDemo?'Todos los accesos y registros de esta demostración son de prueba.':'¿Olvidaste tu contraseña? Técnico: consulta a tu supervisor o administrador. Supervisor: consulta a un administrador. Administrador: otro administrador puede ayudarte. Si es la cuenta maestra o no queda ningún administrador con acceso, utiliza RECUPERAR_ADMIN.bat en la PC principal con la aplicación cerrada.';
  $('auth-mode-info').textContent=setup
    ? 'Primera configuración: crea aquí tu usuario y contraseña de administración.'
    : S.publicDemo
      ? 'Demostración pública con datos ficticios. Elige un acceso de prueba y pulsa Entrar al sistema.'
      : S.demo
      ? 'Estás en la demostración. Completa un acceso de prueba con los botones de abajo y pulsa Entrar al sistema.'
      : 'Instalación normal: usa la cuenta que creaste aquí o la que te asignó tu supervisor. Para probar con cuentas de ejemplo, abre probar_demo.bat.';
  if(S.production)$('auth-mode-info').textContent='Producción local · '+(S.phase>=2?'V34 fase 2':'V33 fase 1')+'. Primer acceso: usuario admin y clave temporal mostrada en la consola de la PC principal. Después debes cambiarla y completar tu perfil.';
  $('demo-login-info').classList.toggle('hidden',!S.demo || setup);
  $('demo-login-info').replaceChildren();
  if(S.demo && !setup) $('demo-login-info').innerHTML=S.publicDemo
    ? '<strong>Demostración pública · Datos ficticios</strong><p>Resultados: <b>visitante_demo</b> / <b>VisitanteDemo2026!</b><br>Captura: <b>90001</b> / <b>90001</b></p><button type="button" class="text-button" id="fill-demo">Ver resultados →</button><br><button type="button" class="text-button" id="fill-demo-technician">Probar captura →</button>'
    : '<strong>Demostración con datos ficticios</strong><p>Supervisión: <b>supervisor_demo</b> / <b>LaboratorioDemo2026!</b><br>Técnico: <b>90001</b> / <b>90001</b></p><button type="button" class="text-button" id="fill-demo">Usar acceso de supervisión →</button><br><button type="button" class="text-button" id="fill-demo-technician">Usar acceso de técnico →</button><p>Si cambiaste una clave de la demo, usa tu clave actual.</p>';
  if($('fill-demo')) $('fill-demo').onclick=()=>{ $('auth-username').value=S.publicDemo?'visitante_demo':'supervisor_demo'; $('auth-password').value=S.publicDemo?'VisitanteDemo2026!':'LaboratorioDemo2026!'; $('auth-submit').focus(); };
  if($('fill-demo-technician')) $('fill-demo-technician').onclick=()=>{ $('auth-username').value='90001'; $('auth-password').value='90001'; $('auth-submit').focus(); };
}
async function loadReferences() {
  const owner=S.user?.id;
  const results=await Promise.all([api('/api/actividades'),api('/api/catalogos'),api('/api/sap'),isVisitor()?Promise.resolve({users:[]}):api('/api/usuarios')]);
  if(!S.user||S.user.id!==owner)return;
  S.activities=results[0].activities || []; S.catalog=results[1]; S.sap=results[2].items || []; S.users=results[3].users || [];
  const current=$('filter-activity').value;
  $('filter-activity').innerHTML=options(S.activities.map((a)=>({value:a.id,label:a.name})),current,'Todas las actividades');
  const people=personOptions().map((u)=>({value:u.id,label:u.name}));
  $('filter-responsible').innerHTML=options(people,$('filter-responsible').value,'Todo el equipo');
  $('capture-responsible').innerHTML=options(people,$('capture-responsible').value || S.user?.id,null);
  $('goal-responsible').innerHTML=options(people,$('goal-responsible').value,'Selecciona técnico');
  $('goal-activity').innerHTML=options(activeActivities().map((a)=>({value:a.id,label:a.name})),$('goal-activity').value,'Selecciona actividad');
  $('filter-voltage').innerHTML=options(S.catalog.voltajes || [],$('filter-voltage').value,'Todos');
  $('filter-condition').innerHTML=options(S.catalog.condiciones || [],$('filter-condition').value,'Todas');
  $('voltage-list').innerHTML=(S.catalog.voltajes || []).map((x)=>`<option value="${escapeHtml(x)}"></option>`).join('');
  $('brands-list').innerHTML=(S.catalog.marcas || []).map((x)=>`<option value="${escapeHtml(x)}"></option>`).join('');
  $('sap-list').innerHTML=S.sap.filter((x)=>x.active).map((x)=>`<option value="${escapeHtml(x.code)}">${escapeHtml(x.voltage)} · ${escapeHtml(x.classification)}</option>`).join('');
}
async function enterApp(me) {
  if(S.user?.id!==me.user.id){for(const name of ['records-table','recent-records','history-results','audit-table'])$(name)?.replaceChildren();window.LabPhaseTwo?.clear();$('base-profile-card')?.remove();$('profile-avatar-editor')?.remove();S.users=[];}
  S.lab=Boolean(me.lab_revision);S.phase=Number(me.delivered_phase)||0;S.installation=me.installation_id||'';
  S.user=me.user; S.production=Boolean(me.production_mode); S.csrf=me.csrf; S.demo=Boolean(me.demo); S.publicDemo=Boolean(me.public_demo); $('auth-view').classList.add('hidden'); $('app-shell').classList.remove('hidden');
  $('account-name').textContent=S.user.name; $('account-role').textContent=roleNames[S.user.role] || S.user.role;
  $('account-avatar').textContent=S.user.name.split(/\s+/).slice(0,2).map((n)=>n[0]).join('').toUpperCase();
  $('demo-badge').textContent=S.demo?'DATOS DE PRUEBA':S.production?'BASE LOCAL · FASE '+(S.phase||1):'PRUEBA LOCAL'; $('environment-label').textContent=`${S.publicDemo?'Demostración pública':S.demo?'Demostración':S.production?'Instalación local':'Versión de pruebas'} · ${me.version || '2.2'}`;
  setRoleVisibility(); if(!S.user.must_change && !S.user.must_complete_profile) await loadReferences();
  if(S.user.must_change || S.user.must_complete_profile) { await navigate('account'); toast(S.user.must_change?'Elige tu contraseña personal para continuar.':'Completa tu perfil para continuar.','warning'); }
  else { $('comparison-group-by').value=isVisitor()?'activity':'technician_activity';await navigate(S.production?(S.phase>=2?'operation':S.user.role==='administrador'?'base':'account'):'dashboard'); }
}
function filterQuery(extra={}) {
  const q=new URLSearchParams();
  for(const [key,id] of [['desde','filter-from'],['hasta','filter-to'],['activity_id','filter-activity'],['sap','filter-sap'],['voltage','filter-voltage'],['brand','filter-brand'],['model','filter-model'],['condition','filter-condition']]) if($(id).value.trim()) q.set(key,$(id).value.trim());
  if(isManager() && $('filter-responsible').value) q.set('responsible_id',$('filter-responsible').value);
  Object.entries(extra).forEach(([key,value])=>{if(value!=='' && value!==undefined && value!==null) q.set(key,String(value));});
  return q.toString();
}
function setFiltersCollapsed(collapsed){$('global-filters').classList.toggle('filter-collapsed',collapsed);$('toggle-filters').setAttribute('aria-expanded',String(!collapsed));}
function updateFilterSummary(){
  let summary=$('filter-summary');if(!summary){summary=document.createElement('p');summary.id='filter-summary';summary.className='filter-summary';$('toggle-filters').after(summary);}
  const parts=[S.view==='comparison'?'Períodos A / B en el configurador':S.view==='receipts'?`Acumulado al ${prettyDate(today())}`:`${prettyDate($('filter-from').value) || 'Inicio del historial'} al ${prettyDate($('filter-to').value) || 'último registro'}`];
  for(const [id,label] of [['filter-activity','Actividad'],['filter-responsible','Técnico'],['filter-sap','SAP'],['filter-voltage','Voltaje'],['filter-brand','Marca'],['filter-model','Modelo'],['filter-condition','Condición']]){
    const input=$(id);if(!input.value || id==='filter-responsible'&&!isManager() || id==='filter-activity'&&['quality','receipts'].includes(S.view))continue;
    parts.push(`${label}: ${input.tagName==='SELECT'?input.selectedOptions[0]?.textContent:input.value}`);
  }
  summary.textContent=parts.join(' · ');
}
pages.base=['BASE LOCAL','Instalación y respaldos','Usuarios, seguridad y copias verificadas · V33 fase 1.'];
const SCREEN_HELP={
  base:['Preparar la instalación','Crea los accesos y configura dos destinos externos de respaldo. Ejecuta una copia de prueba y comprueba su estado.','La captura operativa se habilitará en la fase 2, después de validar esta base. La restauración requiere vista previa, tu contraseña y un motivo.'],
  dashboard:['Del resumen al registro','Elige las fechas y pulsa Aplicar. Toca una tarjeta para ver los datos que forman su número. Toca un punto de la curva para consultar ese intervalo.','Una revisión es una comprobación realizada. La misma serie puede tener varias revisiones; por eso revisiones y medidores distintos son cifras diferentes.'],
  quality:['Entender los resultados de revisión','Toca Aprobadas, Rechazadas o una tasa para ver sus revisiones. En la tabla puedes consultar el trabajo de cada técnico y abrir un hallazgo.','Aprobación = aptas ÷ (aptas + no aptas). Pendientes y sin resultado se muestran aparte. Una calibración fuera de tolerancia requiere revisar sus mediciones.'],
  comparison:['Comparar dos períodos','Selecciona las fechas de A y B, el desglose y pulsa Generar reporte. Toca una cantidad de A o B para consultar sus registros.','La diferencia es B menos A. Si A tiene 20 y B tiene 25, la diferencia es +5 y el crecimiento +25 %. Cuando A es cero, un aumento se muestra Sin base.'],
  records:['Encontrar un registro','Usa los filtros superiores para buscar en todos los registros permitidos. Abre Ver detalle para revisar su información. Corregir y Anular solicitan un motivo.','La lista principal carga páginas del servidor. Buscar en esta tabla solo busca en la página cargada; Anterior y Siguiente de la lista permiten recorrer el resultado completo.'],
  capture:['Registrar una actividad','Selecciona la actividad, fecha y responsable; completa los campos y pulsa Guardar actividad. Fijar actividad permite repetir la captura con el mismo formulario.','La fecha de trabajo es la del trabajo realizado. El sistema conserva quién hizo el trabajo, quién lo registró y cuándo se guardó. Un reingreso añade un registro al historial.'],
  history:['Consultar la historia de un medidor','Escribe la serie completa, incluidos sus ceros iniciales, y pulsa Consultar historial. Abre un registro para ver su información.','La consulta respeta tus permisos. No reemplaza registros anteriores ni reúne equipos diferentes que tengan identificadores distintos.'],
  receipts:['Seguir una orden y sus entregas','Toca una orden o Ver detalle para consultar sus entregas. Registra otra entrega con el mismo proceso, orden y SAP. Cierra el lote cuando el saldo esté completo.','Pendiente = esperado menos recibido, con mínimo cero. Exceso se muestra por separado. Si falta la cantidad esperada, se indica Por confirmar y no se inventa un porcentaje.'],
  goals:['Consultar una meta','Elige un técnico, una actividad, las fechas y la cantidad objetivo. Abre una fila de meta para consultar su producción.','Cada meta corresponde a una actividad y una unidad. Limpiar y sellar el mismo medidor son trabajos distintos; las metas de ambos no se suman como medidores únicos.'],
  activities:['Crear o adaptar una actividad','Usa Crear actividad o Configurar para cambiar sus campos y opciones. Revisa los campos obligatorios antes de guardar.','Cada cambio crea una versión del formulario. Los registros anteriores conservan sus datos y su versión original.'],
  import:['Cargar un archivo sin duplicar registros','Descarga la plantilla, complétala y usa Revisar archivo. Corrige los errores antes de confirmar la carga.','La vista previa todavía no registra producción. Las series, SAP y códigos de empleado deben conservarse como texto para mantener sus ceros iniciales.'],
  catalogs:['Mantener SAP y listas de opciones','Selecciona un código para consultar sus configuraciones o crea otra. Puedes ampliar marcas, voltajes y condiciones desde las listas.','Un SAP puede tener varias configuraciones. Marca y modelo no dependen de un único SAP. Cambiar el catálogo no altera los datos ya registrados.'],
  users:['Administrar los accesos','Agrega técnicos, asigna su perfil y actividades. Restablecer acceso permite ayudar a un técnico que olvidó su clave.','Desactivar un usuario conserva su historial. Las contraseñas actuales no se muestran; el restablecimiento asigna una nueva clave de acceso.'],
  audit:['Saber qué cambió y por qué','Busca una operación y pulsa Ver cambio para comparar los datos anteriores y posteriores.','La auditoría conserva quién hizo el cambio, cuándo y su motivo. Sus entradas no se editan ni se eliminan desde la aplicación.'],
  account:['Consultar tu acceso','Revisa tu nombre y perfil. Para cambiar tu contraseña, escribe la actual y confirma la nueva.','Si olvidas tu contraseña, solicita el restablecimiento al supervisor. Los cambios de clave no borran tu trabajo.']
};
function updateViewHelp(view){
  const help=SCREEN_HELP[view];if(!help)return;
  let node=$('screen-help');if(!node){node=document.createElement('details');node.id='screen-help';node.className='screen-help';document.querySelector('.page-heading').after(node);}
  node.innerHTML=`<summary>Cómo usar esta pantalla</summary><div><h2>${escapeHtml(help[0])}</h2><p>${escapeHtml(help[1])}</p><p class="help-definition">${escapeHtml(help[2])}</p><button type="button" class="text-button" data-guide-open>Ver la guía rápida completa</button></div>`;
}
function openQuickGuide(){
  openDialog('Guía rápida · tocar, consultar y volver',`<div class="quick-guide"><ol><li><strong>Elige qué quieres ver.</strong> Abre Filtros, indica las fechas y pulsa Aplicar. Si estás comparando, define A y B y pulsa Generar reporte.</li><li><strong>Toca el número o el gráfico.</strong> Se abre su lista de datos con las fechas y filtros aplicados. Los botones indican qué puedes consultar.</li><li><strong>Encuentra una fila.</strong> Escribe en Buscar en esta tabla. Pulsa un encabezado para ordenar; vuelve a pulsarlo para invertir el orden.</li><li><strong>Consulta el detalle.</strong> Abre el registro o la orden. Usa Volver a la lista o cierra el panel para seguir explorando sin cambiar tus filtros.</li><li><strong>Descarga lo que necesitas.</strong> CSV de esta vista incluye las filas cargadas que coinciden con la búsqueda. Excel y PDF del informe incluyen el alcance completo indicado en sus filtros.</li></ol><h3>Cómo leer las cifras</h3><p><strong>Aprobación:</strong> de 10 revisiones concluidas, si 8 son aptas y 2 no aptas, la aprobación es 80 %. Las pendientes todavía no entran en esa cuenta.</p><p><strong>Cantidades:</strong> cada actividad conserva su unidad: revisiones, medidores o sellos. Hacer dos trabajos al mismo equipo no significa tener dos equipos.</p><p><strong>Semáforos:</strong> 🟢 resultado completo o aprobado; 🟡 falta información o trabajo por concluir; 🔴 revisa los rechazos, vencimientos, excedentes o hallazgos señalados. El texto de cada alerta explica el caso.</p><h3>Lo que puedes consultar</h3><p>El supervisor consulta el equipo completo. El técnico consulta su trabajo autorizado. El visitante ve totales y desgloses generales, sin series ni información personal.</p><h3>Tus datos se conservan</h3><p>Consultar, buscar y ordenar no cambia registros. En la demo del enlace, cada navegador guarda su propia prueba; usa Descargar respaldo para conservar una copia. En la red de oficina, los equipos que abren el servidor principal comparten su base.</p></div>`);
}
async function navigate(view) {
  if(S.production&&S.phase>=2){view=({capture:'operation',import:'bulk',catalogs:'master',dashboard:S.lab?'labstats':'operation'})[view]||view;}
  if(!pages[view]) view='dashboard';
  if(!isManager() && ['activities','import','catalogs','users','audit'].includes(view)) view='dashboard';
  if(isVisitor() && !['dashboard','quality','comparison','account'].includes(view)) view='dashboard';
  if(S.production && S.phase<2 && !['base','users','audit','account'].includes(view))view=S.user.role==='administrador'?'base':'account';
  if(S.production&&S.phase>=2&&S.user.role!=='administrador'&&['master','activities'].includes(view))view='operation';
  if(S.production && S.user.role!=='administrador' && ['base','audit'].includes(view))view='account';
  if((S.user?.must_change || S.user?.must_complete_profile) && view!=='account') view='account';
  if(S.view!==view)setFiltersCollapsed(true);
  S.view=view; const ticket=++S.navigation; setMenu(false); clearError($('page-error'));
  document.querySelectorAll('.view').forEach((n)=>n.classList.add('hidden')); $(`view-${view}`).classList.remove('hidden');
  document.querySelectorAll('[data-view]').forEach((n)=>n.classList.toggle('active',n.dataset.view===view));
  const title=pages[view]; $('page-eyebrow').textContent=title[0]; $('page-title').textContent=title[1]; $('page-description').textContent=title[2]; $('current-section').textContent=title[1];
  $('global-filters').classList.toggle('hidden',!['dashboard','records','quality','comparison','receipts'].includes(view)); $('quick-capture').classList.toggle('hidden',(S.production&&!S.lab) || isVisitor() || view==='capture' || S.user?.must_change || S.user?.must_complete_profile);
  $('filter-from-wrap').classList.toggle('hidden',view==='comparison' || view==='receipts');$('filter-to-wrap').classList.toggle('hidden',view==='comparison' || view==='receipts');$('filter-activity-wrap').classList.toggle('hidden',view==='quality' || view==='receipts');
  updateFilterSummary();
  $('loading-indicator').classList.remove('hidden');
  try { await ({labstats:()=>LabFlows.panel(''),sealed:()=>LabFlows.panel('sellado'),sapmoves:()=>LabFlows.panel('sap_carga'),operation:()=>S.lab?LabFlows.operation():LabPhaseTwo.operation(),bulk:()=>LabPhaseTwo.bulk(),assignments:()=>LabPhaseTwo.assignments(),scrap:()=>LabPhaseTwo.scrap(),master:()=>LabPhaseTwo.master(),sapload:()=>S.lab?LabFlows.panel('sap_carga'):LabPhaseTwo.sapload(),base:()=>LabFoundation.loadStatus(),dashboard:loadDashboard,quality:loadQuality,comparison:loadComparison,capture:loadCapture,records:loadRecords,history:()=>S.production&&S.phase>=2?LabPhaseTwo.history():Promise.resolve(),activities:loadActivities,import:loadImport,receipts:loadReceipts,goals:loadGoals,users:loadUsers,catalogs:loadCatalogs,audit:loadAudit,account:loadAccount}[view])(); }
  catch(error) { if(ticket===S.navigation) showError($('page-error'),error); }
  finally { if(ticket===S.navigation){$('loading-indicator').classList.add('hidden');updateViewHelp(view);window.LabFoundation?.enhance();window.LabDetails?.enhance();window.LabTables?.enhance();} }
}

const CHART_COLORS={blue:'#39b8ee',green:'#51d69a',red:'#ff7384',amber:'#f2ca66',muted:'#8398b4',a:'#6fa9f1',b:'#f1a654'};
function chartContext() { const from=$('filter-from').value,to=$('filter-to').value;const scope=[`${from || 'Todo el historial'}${to?' al '+to:''}`,S.user?.role==='tecnico'?'Producción propia':'Laboratorio de Medidas'];if(S.view==='quality')scope.push('Actividad: Revisión técnica');for(const [id,label] of [['filter-activity','Actividad'],['filter-responsible','Responsable'],['filter-sap','SAP'],['filter-voltage','Voltaje'],['filter-brand','Marca'],['filter-model','Modelo'],['filter-condition','Condición']]){const input=$(id);if(!input.value || id==='filter-responsible'&&!isManager() || S.view==='quality'&&id==='filter-activity')continue;scope.push(`${label}: ${input.tagName==='SELECT'?input.selectedOptions[0]?.textContent:input.value}`);}return scope.join(' · '); }
function chartFooter(text,limit) {const words=String(text).split(/\s+/),lines=[];let line='';for(let word of words){while(word.length>limit){if(line){lines.push(line);line='';}lines.push(word.slice(0,limit));word=word.slice(limit);}if((line+' '+word).trim().length>limit){lines.push(line);line=word;}else line=(line+' '+word).trim();}if(line)lines.push(line);return lines;}
function chartWidth(id,max=1100){return Math.max(330,Math.min(max,$(id)?.clientWidth || max));}
function chartTip(text,attrs=''){return `tabindex="0" role="img" aria-label="${escapeHtml(text)}" data-chart-tooltip="${escapeHtml(text)}" ${attrs}`;}
function chartPaletteSvg(svg){
  const light=document.documentElement.dataset.theme==='light';
  const p=light?{surface:'#ffffff',grid:'#c6d0de',text:'#172b45',muted:'#42546a',blue:'#1665b4',green:'#14774f',red:'#b8324d',amber:'#946200'}:{surface:'#1e293b',grid:'#526176',text:'#f1f5f9',muted:'#cbd5e1',blue:'#69b4ff',green:'#55d6a0',red:'#ff8796',amber:'#f5ca73'};
  const groups={surface:['#142238'],grid:['#273a53','#2b4059','#2d415a','#32445b'],blue:['#38b9ed','#39b8ee','#3b9ed5','#3cc4f6','#42c3e5','#58c8f0','#60bdf1','#63d4fa','#6bd4f5','#6fa9f1'],green:['#51d69a','#54d69b'],red:['#ff7384'],amber:['#efaa6b','#f1a654','#f2ca66'],text:['#dce9fa','#e0edfc','#e4f1ff','#e5f7ee','#e8f5ff']};
  const map={};for(const [key,colors] of Object.entries(groups))for(const color of colors)map[color]=p[key];
  return svg.replace(/font-size="(9|10)"/g,(_,size)=>`font-size="${size==='9'?11:12}"`).replace(/(fill|stroke|stop-color)="(#[0-9a-f]{6})"/gi,(_,attribute,color)=>`${attribute}="${map[color.toLowerCase()] || p.muted}"`);
}
function installChart(id,title,body,width,plotHeight,context,redraw,data=[],unit=''){
  const lines=chartFooter(context || chartContext(),Math.max(38,Math.floor(width/5.2))),height=plotHeight+lines.length*13+19;
  const svg=chartPaletteSvg(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" class="chart-svg" font-family="Arial,sans-serif" role="img" aria-label="${escapeHtml(title)}"><title>${escapeHtml(title)}</title><desc>${escapeHtml(context || chartContext())}</desc><rect width="${width}" height="${height}" fill="#142238"/><text x="12" y="20" fill="#dce9fa" font-size="12" font-weight="bold">${escapeHtml(title)}</text>${body}${lines.map((line,i)=>`<text x="12" y="${plotHeight+13+i*13}" fill="#a5b8cf" font-size="9">${escapeHtml(line)}</text>`).join('')}</svg>`);
  $(id).innerHTML=svg;S.charts[id.replace('chart-','')]={svg,title,data,unit,redraw};
}
function clearChart(id,message){delete S.charts[id.replace('chart-','')];$(id).innerHTML=empty(message || 'Los datos aparecerán cuando haya actividad en este período.','Sin datos para esta selección');}
function niceMax(value){if(!(value>0))return 1;const magnitude=10**Math.floor(Math.log10(value)),step=[1,2,2.5,5,10].find((x)=>x*magnitude>=value);return step*magnitude;}
function tickDate(point){const date=point.from || point.date || point.start;if(date && /^\d{4}-\d{2}-\d{2}$/.test(date))return new Intl.DateTimeFormat('es-DO',{day:'2-digit',month:'short',timeZone:'UTC'}).format(new Date(`${date}T12:00:00Z`));return point.label;}
function lineChart(id,points,title,unit,context,granularity=$('dashboard-granularity').value){
  if(!points?.length)return clearChart(id);
  const width=chartWidth(id),left=53,right=width-22,top=53,bottom=239,max=niceMax(Math.max(...points.map((p)=>Number(p.value)||0))),span=right-left;
  const x=(i)=>points.length===1?left+span/2:left+i*span/(points.length-1),y=(value)=>bottom-(Number(value)||0)/max*(bottom-top);
  let body=`<defs><linearGradient id="${id}-area" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#38b9ed" stop-opacity=".38"/><stop offset="100%" stop-color="#38b9ed" stop-opacity=".025"/></linearGradient></defs><text x="${left}" y="39" fill="#a8bdd5" font-size="10">${escapeHtml(unit)}</text>`;
  for(let i=0;i<=4;i++){const value=max*i/4,yy=y(value);body+=`<line x1="${left}" x2="${right}" y1="${yy}" y2="${yy}" stroke="#32445b" stroke-dasharray="3 4"/><text x="${left-9}" y="${yy+4}" text-anchor="end" fill="#a5b9d1" font-size="10">${escapeHtml(fmt(value))}</text>`;}
  const path=points.map((p,i)=>`${i?'L':'M'}${x(i).toFixed(2)},${y(p.value).toFixed(2)}`).join(' ');
  if(points.length>1)body+=`<path d="${path} L${x(points.length-1)},${bottom} L${x(0)},${bottom} Z" fill="url(#${id}-area)"/><path d="${path}" fill="none" stroke="#3cc4f6" stroke-width="2.7" stroke-linejoin="round"/>`;
  const step=Math.max(1,Math.ceil(points.length/(width<500?4:8))),valueStep=Math.max(1,Math.ceil(points.length/(width<500?5:14)));
  body+=points.map((p,i)=>{const text=`${p.label}${p.from?' · '+p.from+' al '+p.to:''}: ${fmt(p.value)} ${unit}${p.records===undefined?'':' · '+fmt(p.records)+' registros'}`;return `<g ${chartTip(text,`data-value="${Number(p.value)||0}" data-date="${escapeHtml(p.from || p.date || p.label)}" data-series="${escapeHtml(title)}"`)}><title>${escapeHtml(text)}</title><circle cx="${x(i)}" cy="${y(p.value)}" r="9" fill="transparent"/><circle cx="${x(i)}" cy="${y(p.value)}" r="3.7" fill="#63d4fa" stroke="#142238" stroke-width="1.5"/>${i%valueStep===0 || i===points.length-1?`<text x="${x(i)}" y="${Math.max(top-5,y(p.value)-11)}" fill="#e8f5ff" text-anchor="middle" font-size="10" font-weight="bold">${escapeHtml(fmt(p.value))}</text>`:''}</g>${i%step===0 || i===points.length-1?`<text x="${x(i)}" y="${bottom+22}" fill="#b4c7de" text-anchor="${i===0?'start':i===points.length-1?'end':'middle'}" font-size="10">${escapeHtml(tickDate(p))}</text>`:''}`;}).join('');
  body+=`<text x="${right}" y="${bottom+41}" text-anchor="end" fill="#8ea6c2" font-size="9">Fecha de trabajo · ${escapeHtml(granularityLabel(granularity))}</text>`;
  installChart(id,title,body,width,295,`${context} · Unidad: ${unit} · Intervalos sin producción = 0.`,()=>lineChart(id,points,title,unit,context,granularity),points,unit);
}
function columnChart(id,data,title,defaultUnit='registros',context=chartContext()){
  if(!data?.length || !data.some((x)=>Number(x.value)))return clearChart(id);
  const width=chartWidth(id),groups=new Map();for(const row of data){const unit=row.unit || defaultUnit;if(!groups.has(unit))groups.set(unit,[]);groups.get(unit).push(row);}
  let body='',offset=39;
  for(const [unit,allRows] of groups){const rows=allRows.slice(0,12),left=46,right=width-17,top=offset+32,bottom=offset+191,max=niceMax(Math.max(...rows.map((r)=>Number(r.value)||0))),slot=(right-left)/rows.length,bar=Math.min(65,slot*.58);
    body+=`<text x="12" y="${offset+9}" fill="#9dc5e9" font-size="11" font-weight="bold">${escapeHtml(unit)}</text>`;
    for(let i=0;i<=4;i++){const v=max*i/4,yy=bottom-v/max*(bottom-top);body+=`<line x1="${left}" x2="${right}" y1="${yy}" y2="${yy}" stroke="#2b4059" stroke-dasharray="3 4"/><text x="${left-8}" y="${yy+4}" fill="#9eb3cd" font-size="10" text-anchor="end">${fmt(v)}</text>`;}
    body+=rows.map((row,i)=>{const value=Number(row.value)||0,x=left+slot*(i+.5),h=value/max*(bottom-top),label=String(row.label || 'Sin informar'),words=chartFooter(label,Math.max(6,Math.floor(slot/5.8))).slice(0,3),tip=`${label}: ${fmt(value)} ${unit}`;return `<g ${chartTip(tip,`data-value="${value}" data-series="${escapeHtml(label)}" data-unit="${escapeHtml(row.unit || unit)}"`)}><title>${escapeHtml(tip)}</title><rect x="${x-bar/2}" y="${bottom-h}" width="${bar}" height="${Math.max(.5,h)}" rx="3" fill="${i%2?'#3b9ed5':'#42c3e5'}"/><text x="${x}" y="${bottom-h-8}" fill="#e4f1ff" font-size="11" font-weight="bold" text-anchor="middle">${fmt(value)}</text>${words.map((word,j)=>`<text x="${x}" y="${bottom+18+j*12}" text-anchor="middle" fill="#b9cbe0" font-size="9">${escapeHtml(word)}</text>`).join('')}</g>`;}).join('');
    if(allRows.length>12)body+=`<text x="12" y="${bottom+64}" fill="#a6bbd5" font-size="9">Se muestran 12 de ${allRows.length} categorías; consulta el detalle para el resto.</text>`;
    offset+=275;
  }
  installChart(id,title,body,width,offset+4,context,()=>columnChart(id,data,title,defaultUnit,context),data,defaultUnit);
}
// Horizontal ranking is used only for comparable frequencies (people or failure types).
function svgChart(id,data,title,unit='registros',context=chartContext()){
  if(!data?.length || !data.some((x)=>Number(x.value)))return clearChart(id);
  const width=chartWidth(id,850),rows=data.slice(0,12),left=12,right=width-65,max=Math.max(...rows.map((r)=>Number(r.value)||0),1),rowHeight=48;
  const body=rows.map((row,i)=>{const yy=52+i*rowHeight,value=Number(row.value)||0,label=String(row.label || 'Sin informar'),display=label.length>Math.floor(width/7)?label.slice(0,Math.floor(width/7)-1)+'…':label,tip=`${label}: ${fmt(value)} ${row.unit || unit}`;return `<g ${chartTip(tip,`data-value="${value}" data-series="${escapeHtml(label)}" data-unit="${escapeHtml(row.unit || unit)}"`)}><title>${escapeHtml(tip)}</title><text x="${left}" y="${yy}" fill="#bdcee3" font-size="11">${escapeHtml(display)}</text><rect x="${left}" y="${yy+9}" width="${right-left}" height="10" rx="4" fill="#273a53"/><rect x="${left}" y="${yy+9}" width="${(right-left)*value/max}" height="10" rx="4" fill="${id==='chart-quality-failures'?'#efaa6b':'#60bdf1'}"/><text x="${width-12}" y="${yy+17}" text-anchor="end" fill="#e0edfc" font-size="12" font-weight="bold">${fmt(value)}</text></g>`;}).join('');
  installChart(id,title,body,width,68+rows.length*rowHeight,`${context} · Unidad: ${unit}${data.length>12?` · 12 de ${data.length} categorías visibles`:''}`,()=>svgChart(id,data,title,unit,context),data,unit);
}
function qualityDonut(id,summary,context=chartContext()){
  const width=chartWidth(id,650),cx=width<420?96:145,cy=133,r=68,circ=2*Math.PI*r,approved=Number(summary.approved)||0,rejected=Number(summary.rejected)||0,evaluated=approved+rejected,rate=evaluated?approved/evaluated*100:null,green=evaluated?approved/evaluated*circ:0,red=evaluated?rejected/evaluated*circ:0,lx=width<420?191:265;
  let body=`<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="#2d415a" stroke-width="18"/>`;
  if(evaluated){body+=`<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="#54d69b" stroke-width="18" stroke-dasharray="${green} ${circ-green}" transform="rotate(-90 ${cx} ${cy})"/><circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="#ff7384" stroke-width="18" stroke-dasharray="${red} ${circ-red}" stroke-dashoffset="${-green}" transform="rotate(-90 ${cx} ${cy})"/>`;}
  body+=`<g ${chartTip(evaluated?`Aprobación: ${percent(rate)} · ${fmt(approved)} aprobadas de ${fmt(evaluated)} evaluadas`:'Sin evaluaciones concluidas',`data-value="${rate===null?'':rate}" data-series="Aprobación"`)}><title>${evaluated?`${fmt(approved)} / ${fmt(evaluated)} evaluadas`:'Sin evaluaciones'}</title><text x="${cx}" y="${cy+2}" fill="#e5f7ee" font-size="${width<420?24:30}" font-weight="bold" text-anchor="middle">${rate===null?'—':percent(rate)}</text><text x="${cx}" y="${cy+23}" fill="#9eb5ca" font-size="10" text-anchor="middle">${evaluated?'APROBACIÓN':'SIN EVALUACIONES'}</text></g>`;
  const values=[['Aprobadas',approved,CHART_COLORS.green],['Rechazadas',rejected,CHART_COLORS.red],['Pendientes',Number(summary.pending)||0,CHART_COLORS.amber],['Sin resultado',Number(summary.without_result)||0,CHART_COLORS.muted]];
  body+=values.map(([label,value,color],i)=>`<g ${chartTip(`${label}: ${fmt(value)} revisiones`,`data-value="${value}" data-series="${label}"`)}><title>${label}: ${fmt(value)}</title><circle cx="${lx}" cy="${73+i*40}" r="4" fill="${color}"/><text x="${lx+12}" y="${76+i*40}" fill="#bfd0e3" font-size="10">${label}</text><text x="${lx+12}" y="${93+i*40}" fill="${color}" font-size="16" font-weight="bold">${fmt(value)}</text></g>`).join('');
  body+=`<text x="12" y="247" fill="#c0d4e9" font-size="11">Denominador: ${fmt(evaluated)} evaluadas = ${fmt(approved)} aptas + ${fmt(rejected)} no aptas.</text>`;
  installChart(id,'Resultados de revisión técnica',body,width,270,`${context} · Pendientes y sin resultado fuera de las tasas. Las cifras representan revisiones, no medidores únicos.`,()=>qualityDonut(id,summary,context),values.map(([label,value])=>({label,value})),'revisiones');
}
function metricCards(items) {
  return items.map(([label,value,note,tone=''])=>`<article class="metric-card ${escapeHtml(tone)}"><span class="metric-label">${escapeHtml(label)}</span><strong class="metric-value">${value===null || value===undefined?'—':typeof value==='string'?escapeHtml(value):fmt(value)}</strong><span class="metric-note">${escapeHtml(note || '')}</span></article>`).join('');
}
function signalBadge(signal,label) {const color=signal==='verde'?'good':signal==='rojo'?'danger':'warn',icon=signal==='verde'?'🟢':signal==='rojo'?'🔴':'🟡';return `<span class="badge ${color} operational-signal"><span aria-hidden="true">${icon}</span>${escapeHtml(label)}</span>`;}
function percent(value) {return value===null || value===undefined?'—':`${fmt(value)} %`;}
function signed(value) {return value>0?`+${fmt(value)}`:fmt(value);}
function variation(value,state) {return value===null || state==='sin_base'?'Sin base':`${signed(value)} %`;}
function granularityLabel(value) {return ({diaria:'Diaria',semanal:'Semanal · semana ISO',mensual:'Mensual',anual:'Anual'})[value] || value;}
function initialAvatar(name){return String(name || '?').trim().split(/\s+/).slice(0,2).map((part)=>part[0]).join('').toUpperCase();}
function personCell(name,username='',personId=null){
  const person=(S.users || []).find((user)=>personId!==null?String(user.id)===String(personId):username && user.username===username);
  const role=person?.role || 'persona',color=person?.avatar_color;
  const avatar=window.LabAvatars?LabAvatars.render({name,role,color,size:36,decorative:true}):escapeHtml(initialAvatar(name));
  return `<div class="person-cell"><span class="person-avatar" data-avatar-host data-avatar-user-id="${escapeHtml(person?.id || personId || '')}" data-avatar-username="${escapeHtml(username)}" data-avatar-name="${escapeHtml(name)}" data-avatar-role="${escapeHtml(role)}" aria-hidden="true">${avatar}</span><div><strong class="person-name">${escapeHtml(name || 'Sin responsable')}</strong>${username?`<small class="person-meta">${escapeHtml(username)}</small>`:''}</div></div>`;
}
function sparkline(points,unit='revisiones'){
  if(!points?.length)return '<span class="muted">Sin serie</span>';
  const values=points.map((p)=>Number(p.value)||0),max=Math.max(...values,1),width=88,height=29,x=(i)=>values.length===1?44:3+i*82/(values.length-1),y=(value)=>25-value/max*21,description=points.map((p)=>`${p.label}: ${fmt(p.value)} ${unit}`).join('; ');
  return `<span class="sparkline"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(description)}"><title>${escapeHtml(description)}</title>${values.length>1?`<path d="${values.map((v,i)=>`${i?'L':'M'}${x(i)},${y(v)}`).join(' ')}" fill="none" stroke="#58c8f0" stroke-width="2"/>`:''}${values.length<=35?values.map((v,i)=>`<circle cx="${x(i)}" cy="${y(v)}" r="1.6" fill="#6bd4f5"/>`).join(''):''}</svg></span>`;
}
function heroCard(label,value,note,icon,tone,metric){return `<article class="metric-card hero-card kpi-${tone}" data-metric="${metric}" data-value="${escapeHtml(value)}"><div class="hero-icon" aria-hidden="true">${icon}</div><div class="hero-content"><span class="metric-label">${escapeHtml(label)}</span><strong class="metric-value">${typeof value==='string'?escapeHtml(value):fmt(value)}</strong><span class="metric-note">${escapeHtml(note)}</span></div></article>`;}
function receiptContext(){const filters=[['filter-sap','SAP'],['filter-voltage','Voltaje'],['filter-brand','Marca'],['filter-model','Modelo'],['filter-condition','Condición']].filter(([id])=>$(id).value).map(([id,label])=>`${label}: ${$(id).value}`);const cutoff=S.view==='dashboard'?($('filter-to').value || today()):today();return `Estado al ${cutoff} · Acumulado de entregas en medidores hasta el corte; Desde no aplica${filters.length?' · '+filters.join(' · '):''}`;}
async function loadDashboard(){
  const context=chartContext(),receiptScope=receiptContext(),query=filterQuery({granularity:$('dashboard-granularity').value}),data=await api(`/api/dashboard?${query}`);S.dashboard=data;S.dashboardQuery=query;S.dashboardContext=context;S.dashboardReceiptContext=receiptScope;
  const q=data.summary_quality || {total:data.review_count,approved:0,rejected:0,evaluated:0,approval_rate:null};
  const meter='<svg viewBox="0 0 48 56" width="42" height="49" fill="none"><rect x="6" y="3" width="36" height="46" rx="9" stroke="currentColor" stroke-width="2.5"/><rect x="12" y="11" width="24" height="11" rx="2" fill="currentColor" fill-opacity=".18" stroke="currentColor"/><circle cx="24" cy="34" r="6" stroke="currentColor" stroke-width="2"/><path d="M24 30v5l4 2M14 49v5m20-5v5" stroke="currentColor" stroke-width="2"/></svg>';
  const ring=`<span class="hero-ring"><svg viewBox="0 0 64 64" width="64" height="64" fill="none"><circle cx="32" cy="32" r="25" stroke="#2d415b" stroke-width="7"/><circle cx="32" cy="32" r="25" stroke="#39b8ee" stroke-width="7" stroke-dasharray="${(q.approval_rate || 0)/100*157.08} 157.08" transform="rotate(-90 32 32)"/><text x="32" y="38" fill="#b8dcf9" text-anchor="middle" font-size="19" font-family="Arial,sans-serif">%</text></svg></span>`;
  $('metrics-grid').innerHTML=heroCard('Revisiones realizadas',q.total ?? data.review_count,'Revisiones válidas en el período',meter,'blue','reviews')+heroCard('Revisiones aprobadas',q.approved,'Resultado técnico: Apto','✓','green','approved')+heroCard('Revisiones rechazadas',q.rejected,'Resultado técnico: No apto','✕','red','rejected')+heroCard('Tasa de aprobación',q.evaluated?percent(q.approval_rate):'—',q.evaluated?`${fmt(q.approved)} / ${fmt(q.evaluated)} evaluadas`:'Sin evaluaciones concluidas',ring,'amber','approval-rate');
  $('dashboard-scope').innerHTML=[['Registros de actividad',data.event_count],['Series identificadas',data.identified_unique],['Reingresos de revisión',data.reentries],['Lotes pendientes',data.receipts_pending],['Revisiones sin concluir',(q.pending || 0)+(q.without_result || 0)]].map(([label,value])=>`<div class="scope-stat"><strong>${fmt(value)}</strong><span>${label}</span></div>`).join('');
  $('unit-summary').innerHTML=Object.entries(data.totals_by_unit || {}).map(([unit,value])=>`<span class="unit-chip"><strong>${fmt(value)}</strong> ${escapeHtml(unit)}</span>`).join('')+'<span class="muted">Cantidades por unidad. Los registros y las revisiones no equivalen a medidores físicos únicos.</span>';
  const previous=$('dashboard-series').value,series=data.trend?.series || [];
  $('dashboard-series').innerHTML=options(series.map((row)=>({value:row.id,label:`${row.activity_name} · ${row.unit}`})),series.some((r)=>r.id===previous)?previous:(series.find((r)=>r.activity_id==='revision')?.id || series[0]?.id),null);
  renderDashboardTrend();renderDashboardBatches();
  columnChart('chart-activity',data.by_activity,'Cantidades por actividad y unidad','unidades');columnChart('chart-voltage',data.by_voltage,'Registros por voltaje','registros');if(isManager())svgChart('chart-collaborator',data.by_collaborator,'Registros por responsable','registros');else delete S.charts.collaborator;
  $('dashboard-goals').innerHTML=renderGoals(data.goals || [],true);
}
function renderDashboardTrend(){
  const trend=S.dashboard?.trend,series=trend?.series?.find((row)=>String(row.id)===$('dashboard-series').value);
  if(!series){$('dashboard-trend-meta').textContent='Selecciona un período con producción.';clearChart('chart-day');return;}
  $('dashboard-trend-meta').innerHTML=`<strong>${fmt(series.total)} ${escapeHtml(series.unit)}</strong><span>${escapeHtml(trend.from)} al ${escapeHtml(trend.to)}</span>`;
  const context=`${S.dashboardContext} · Serie: ${series.activity_name} · ${granularityLabel(trend.granularity)}`;
  lineChart('chart-day',series.points,`${series.activity_name} · ${series.unit}`,series.unit,context,trend.granularity);
  let detail=$('dashboard-trend-table');if(!detail){detail=document.createElement('details');detail.id='dashboard-trend-table';detail.className='chart-details';$('chart-day').after(detail);}detail.innerHTML=`<summary>Ver cantidades exactas por intervalo</summary>${table(['Intervalo','Desde','Hasta',series.unit,'Registros'],(series.points || []).map((p)=>[escapeHtml(p.label),escapeHtml(p.from || p.start),escapeHtml(p.to || p.end),fmt(p.value),fmt(p.records)]))}`;
}
function orderProgress(order){if(order.expected===null || order.expected===undefined)return '<span class="muted">Esperado por confirmar</span>';const n=order.progress_pct ?? (order.expected?order.received/order.expected*100:null);if(n===null)return '<span class="muted">Sin cantidad esperada</span>';return `<div class="order-progress"><progress class="lot-bar ${order.signal==='rojo'?'is-red':order.signal==='verde'?'is-green':''}" value="${Math.min(100,Math.max(0,n))}" max="100" aria-label="Avance de recepción: ${escapeHtml(percent(n))}"></progress><strong>${percent(n)}</strong></div>`;}
function renderDashboardBatches(){
  const data=S.dashboard,rows=data.batch_progress || [],shown=rows.slice(0,10),summary=data.receipt_summary || {};
  $('dashboard-lots-note').textContent=`${S.dashboardReceiptContext}. ${fmt(summary.pending_total)} medidores pendientes en órdenes con esperado confirmado${summary.unknown_orders?`; ${fmt(summary.unknown_orders)} órdenes por confirmar`:''}.`;
  $('dashboard-lots').innerHTML=shown.length?`<div class="lot-list">${shown.map((o)=>`<div class="lot-row"><div class="lot-identity"><strong>${escapeHtml(o.process)}</strong><small>Orden ${escapeHtml(o.order_number)} · SAP ${escapeHtml(o.sap || 'Sin informar')}</small></div><div class="lot-amount"><strong>${fmt(o.received)} <span>/ ${o.expected===null?'Por confirmar':fmt(o.expected)}</span></strong><small>${o.pending===null?'Saldo por confirmar':`${fmt(o.pending)} pendientes`}${o.excess?` · ${fmt(o.excess)} en exceso`:''}</small></div>${orderProgress(o)}<div class="lot-status">${signalBadge(o.signal,orderStateLabel(o))}${o.due_date?`<small class="table-subline">Límite: ${escapeHtml(prettyDate(o.due_date))}</small>`:''}</div></div>`).join('')}</div>${rows.length>10?`<p class="table-note">Se muestran 10 de ${fmt(rows.length)} lotes; consulta Recepciones para el detalle.</p>`:''}`:empty('No hay órdenes dentro de los filtros seleccionados.','Sin lotes en seguimiento');
  batchChart(rows,S.dashboardReceiptContext);
}
function batchChart(rows,context=receiptContext()){
  if(!rows?.length)return clearChart('chart-batch-progress','No hay órdenes con estos filtros.');
  const id='chart-batch-progress',width=chartWidth(id,1000),shown=rows.slice(0,16),left=12,right=width-100,rowHeight=62;
  const body=shown.map((o,i)=>{const yy=52+i*rowHeight,has=o.expected!==null && o.expected!==undefined && o.expected>0,n=has?o.received/o.expected*100:null,tip=`${o.process} · SAP ${o.sap || 'Sin informar'} · ${fmt(o.received)} recibidos / ${has?fmt(o.expected):'Por confirmar'} esperados · Pendiente ${o.pending===null?'Por confirmar':fmt(o.pending)}${o.excess?' · Exceso '+fmt(o.excess):''}`;return `<g ${chartTip(tip,`data-value="${n===null?'':n}" data-series="${escapeHtml(o.process)}"`)}><title>${escapeHtml(tip)}</title><text x="12" y="${yy}" fill="#d4e3f5" font-size="11">${escapeHtml(o.process)} · ${fmt(o.received)} / ${has?fmt(o.expected):'Por confirmar'}</text><rect x="${left}" y="${yy+9}" width="${right-left}" height="12" rx="5" fill="#2e4158"/>${has?`<rect x="${left}" y="${yy+9}" width="${(right-left)*Math.min(1,o.received/o.expected)}" height="12" rx="5" fill="${o.signal==='rojo'?CHART_COLORS.red:o.signal==='verde'?CHART_COLORS.green:CHART_COLORS.blue}"/>`:''}<text x="${width-12}" y="${yy+19}" text-anchor="end" fill="#dfedfc" font-size="11">${n===null?'Sin base':percent(n)}</text><text x="12" y="${yy+38}" fill="#a6bcd5" font-size="9">${escapeHtml(orderStateLabel(o))}${o.due_date?' · Límite '+o.due_date:''}</text></g>`;}).join('');
  installChart(id,'Avance de recepción por lote',body,width,58+shown.length*rowHeight,`${context} · Barras: recibido / esperado, escala 0–100 %. Los excesos conservan su porcentaje numérico.${rows.length>16?' Se muestran 16 lotes de '+rows.length+'.':''}`,()=>batchChart(rows,context),rows,'medidores');
}
function qualityState(row){return row.traffic_light==='rojo'?'Revisar hallazgos':row.traffic_light==='verde'?'Evaluaciones aprobadas':'Evaluación pendiente';}
async function loadQuality(){
  const query=new URLSearchParams(filterQuery({granularity:$('quality-granularity').value}));query.delete('activity_id');
  const data=await api(`/api/calidad?${query}`),q=data.summary;S.quality=data;S.qualityQuery=query.toString();
  $('quality-status').innerHTML=signalBadge(q.traffic_light,qualityState(q));
  $('quality-metrics').innerHTML=metricCards([['Revisiones técnicas',q.total,'Registros válidos en el período'],['Tasa de aprobación',percent(q.approval_rate),`${fmt(q.approved)} aptas / ${fmt(q.evaluated)} evaluadas`,'kpi-green'],['Tasa de rechazo',percent(q.rejection_rate),`${fmt(q.rejected)} no aptas / ${fmt(q.evaluated)} evaluadas`,'kpi-red'],['Sin concluir',(q.pending || 0)+(q.without_result || 0),`${fmt(q.pending)} pendientes · ${fmt(q.without_result)} sin resultado`],['Mediciones de calibración',q.calibrations,'Con referencia y medición'],['Fuera de tolerancia',q.calibrations_outside_tolerance,'Magnitud de desviación superior al límite'],['Desviación media',percent(q.mean_deviation_pct),'Promedio de desviaciones con signo'],['Desviación absoluta media',percent(q.mean_absolute_deviation_pct),'Promedio de la magnitud de desviación']]);
  $('quality-denominator').textContent=`Base de las tasas: ${fmt(q.evaluated)} evaluaciones concluidas = ${fmt(q.approved)} aptas + ${fmt(q.rejected)} no aptas. Pendientes: ${fmt(q.pending)}; sin resultado: ${fmt(q.without_result)}. Una revisión repetida vuelve a contar como revisión.`;
  qualityDonut('chart-quality-results',q);svgChart('chart-quality-failures',data.by_failure || [],'Frecuencia de fallos informados','revisiones');
  const scopes=data.target_scope_labels || {};
  $('quality-technicians').innerHTML=table(['Técnico responsable','Producción exacta','Tendencia de revisiones','Meta del período','Desviación vs. meta','Aprobación','Rechazo','Fuera de tolerancia','Desviación de medición','Estado de calidad'],(data.by_technician || []).map((row)=>{
    const quantity=row.produced_quantity ?? (row.quantities_by_unit?null:row.total),target=row.assigned_target,scope=scopes[row.target_scope] || 'Sin meta exacta para este alcance',delta=quantity!==null && target!==null && target!==undefined?quantity-target:null;
    return [personCell(row.name,row.username),`<strong class="production-value">${quantity===null?Object.entries(row.quantities_by_unit || {}).map(([unit,value])=>`${fmt(value)} ${escapeHtml(unit)}`).join('<br>'):`${fmt(quantity)} ${escapeHtml(row.unit || 'revisiones')}`}</strong><small>${fmt(row.total)} revisiones · ${fmt(row.evaluated)} evaluadas</small>`,sparkline(row.trend,'registros de revisión'),target===null || target===undefined?`<span title="${escapeHtml(scope)}">Sin meta exacta</span>`:`<strong>${fmt(target)} ${escapeHtml(row.unit)}</strong>${progress(row.attainment)}`,delta===null?'—':`<span class="numeric-change ${delta<0?'negative':delta>0?'positive':''}">${signed(delta)}</span>`,`${percent(row.approval_rate)}<small>${fmt(row.approved)} aptas</small>`,`${percent(row.rejection_rate)}<small>${fmt(row.rejected)} no aptas / ${fmt(row.evaluated)}</small>`,fmt(row.calibrations_outside_tolerance),`${percent(row.mean_deviation_pct)}<small>Absoluta: ${percent(row.mean_absolute_deviation_pct)}</small>`,signalBadge(row.traffic_light,qualityState(row))];
  }));
  $('quality-technicians').querySelector('table')?.classList.add('analytics-table','quality-tech-table');
  renderQualityFailures();
  $('quality-period-label').textContent=`${granularityLabel(data.period?.granularity || $('quality-granularity').value)} · ${data.period?.desde || $('filter-from').value || 'Inicio del historial'} al ${data.period?.hasta || $('filter-to').value || today()}`;
  $('quality-timeline').innerHTML=table(['Intervalo','Revisiones','Aprobadas','Rechazadas','Pendientes','Sin resultado','Aprobación','Fuera de tolerancia'],(data.by_period || []).map((row)=>[escapeHtml(row.label),fmt(row.total),fmt(row.approved),fmt(row.rejected),fmt(row.pending),fmt(row.without_result),percent(row.approval_rate),fmt(row.calibrations_outside_tolerance)]));
  for(const format of ['xlsx','pdf'])$(`quality-export-${format}`).href=`/api/calidad.${format}?${query}`;
}
function renderQualityFailures(){const data=S.quality,rows=data.detailed_failures || [];
  $('quality-failures-note').textContent=`${fmt(rows.length)} de ${fmt(data.failure_count ?? rows.length)} hallazgos mostrados. Se conserva el texto registrado; no se asigna severidad automáticamente.`;
  $('quality-failures-table').innerHTML=table(['Serie del medidor','Fallo informado','Fecha de trabajo','Responsable técnico','Inspección','Resultado'],rows.map((row)=>[`<strong class="mono">${escapeHtml(row.serial || 'Sin serie informada')}</strong>`,escapeHtml(row.failure),escapeHtml(prettyDate(row.work_date)),personCell(row.responsible_name,row.responsible_username),escapeHtml(row.inspection_type || 'Sin informar'),`${escapeHtml(row.result || 'Sin resultado')}${row.outside_tolerance?'<small class="danger-text">Fuera de tolerancia</small>':''}`]),'No se informaron fallos en estas revisiones.');
  $('quality-failures-table').querySelector('table')?.classList.add('analytics-table','quality-fault-table');
  if(data.failure_has_more){const button=document.createElement('button');button.id='quality-failures-more';button.className='btn secondary';button.textContent='Mostrar más hallazgos';button.onclick=()=>busy(button,async()=>{const query=new URLSearchParams(S.qualityQuery);query.set('failure_offset',String(rows.length));const more=await api(`/api/calidad?${query}`);S.quality.detailed_failures=[...rows,...more.detailed_failures];S.quality.failure_has_more=more.failure_has_more;renderQualityFailures();});$('quality-failures-table').append(button);}
}
function comparisonChart(data,filterContext=comparisonFilterContext()){
  const rows=data.rows || [];if(!rows.length)return clearChart('chart-comparison','No hay producción en los períodos elegidos.');
  const id='chart-comparison',width=chartWidth(id),groups=new Map();for(const row of rows){if(!groups.has(row.unit))groups.set(row.unit,[]);groups.get(row.unit).push(row);}
  let body='',offset=39;
  for(const [unit,allRows] of groups){const shown=allRows.slice(0,10),left=49,right=width-16,top=offset+36,bottom=offset+224,max=niceMax(Math.max(...shown.flatMap((r)=>[r.a,r.b]))),slot=(right-left)/shown.length,bw=Math.min(36,slot*.32);
    body+=`<text x="12" y="${offset+12}" fill="#a5c8ec" font-size="11" font-weight="bold">${escapeHtml(unit)} · A referencia / B comparado</text>`;
    for(let i=0;i<=4;i++){const value=max*i/4,yy=bottom-value/max*(bottom-top);body+=`<line x1="${left}" x2="${right}" y1="${yy}" y2="${yy}" stroke="#2c415b" stroke-dasharray="3 4"/><text x="${left-8}" y="${yy+4}" text-anchor="end" fill="#a8bcd5" font-size="10">${fmt(value)}</text>`;}
    body+=shown.map((row,i)=>{const x=left+slot*(i+.5),name=[row.responsible_name,row.activity_name].filter(Boolean).join(' · '),lines=chartFooter(name,Math.max(6,Math.floor(slot/5.9))).slice(0,3);return ['a','b'].map((period,j)=>{const value=Number(row[period])||0,h=value/max*(bottom-top),tip=`${name} · Período ${period.toUpperCase()}: ${fmt(value)} ${unit}`;return `<g ${chartTip(tip,`data-value="${value}" data-series="${period.toUpperCase()}" data-category="${escapeHtml(name)}" data-responsible-id="${row.responsible_id ?? ''}" data-activity-id="${escapeHtml(row.activity_id || '')}" data-unit="${escapeHtml(unit)}"`)}><title>${escapeHtml(tip)}</title><rect x="${x+(j?2:-bw-2)}" y="${bottom-h}" width="${bw}" height="${Math.max(h,.5)}" rx="2" fill="${j?CHART_COLORS.b:CHART_COLORS.a}"/><text x="${x+(j?bw/2+2:-bw/2-2)}" y="${bottom-h-7}" text-anchor="middle" fill="${j?'#ffd39e':'#b8d8ff'}" font-size="${shown.length>6?9:11}">${fmt(value)}</text></g>`;}).join('')+lines.map((line,j)=>`<text x="${x}" y="${bottom+19+j*12}" text-anchor="middle" fill="#bacce3" font-size="9">${escapeHtml(line)}</text>`).join('');}).join('');
    if(allRows.length>10)body+=`<text x="12" y="${bottom+67}" fill="#a6bdd6" font-size="9">10 de ${allRows.length} filas representadas; la tabla conserva todas.</text>`;offset+=310;
  }
  const filters=filterContext;installChart(id,'Comparación de cantidades A / B',body,width,offset,`A referencia: ${data.period_a.from} al ${data.period_a.to} · B comparado: ${data.period_b.from} al ${data.period_b.to} · ${filters} · Ejes separados por unidad; escala compartida dentro de cada panel.`,()=>comparisonChart(data,filterContext),rows,'por unidad');
}
function comparisonFilterContext(){const labels=[['filter-activity','Actividad'],['filter-responsible','Responsable'],['filter-sap','SAP'],['filter-voltage','Voltaje'],['filter-brand','Marca'],['filter-model','Modelo'],['filter-condition','Condición']];return [S.user?.role==='tecnico'?'Producción propia':'Laboratorio de Medidas',...labels.filter(([id])=>$(id).value && (id!=='filter-responsible' || isManager())).map(([id,label])=>`${label}: ${$(id).tagName==='SELECT'?$(id).selectedOptions[0]?.textContent:$(id).value}`)].join(' · ');}

function setComparisonDefaults() {
  const day=today(),end=new Date(`${day}T12:00:00Z`),start=new Date(Date.UTC(end.getUTCFullYear(),end.getUTCMonth(),1,12)),previousEnd=new Date(start.valueOf()-86400000),duration=Math.round((end-start)/86400000),previousStart=new Date(previousEnd.valueOf()-duration*86400000);
  const iso=(value)=>value.toISOString().slice(0,10);
  $('comparison-a-from').value=iso(previousStart);$('comparison-a-to').value=iso(previousEnd);$('comparison-b-from').value=iso(start);$('comparison-b-to').value=day;
}
function comparisonQuery() {
  const query=new URLSearchParams(filterQuery());query.delete('desde');query.delete('hasta');
  for(const [name,id] of [['a_desde','comparison-a-from'],['a_hasta','comparison-a-to'],['b_desde','comparison-b-from'],['b_hasta','comparison-b-to'],['granularity','comparison-granularity'],['group_by','comparison-group-by']])query.set(name,$(id).value);
  if(!query.get('a_desde') || !query.get('a_hasta') || !query.get('b_desde') || !query.get('b_hasta'))throw new Error('Completa las cuatro fechas de los períodos.');
  if(query.get('a_desde')>query.get('a_hasta') || query.get('b_desde')>query.get('b_hasta'))throw new Error('La fecha inicial de cada período debe ser anterior o igual a su fecha final.');
  return query;
}
function deltaClass(value,invert=false){return value===null || value===undefined || value===0?'neutral':(value>0)!==invert?'positive':'negative';}
function comparisonStatus(row){if(row.a===0 && row.b>0)return signalBadge('amarillo','Sin base de comparación');if(row.delta>0)return signalBadge('verde','Mayor producción');if(row.delta<0)return signalBadge('rojo','Menor producción');return signalBadge('amarillo','Sin variación');}
function comparisonTable(data){
  const group=data.group_by || $('comparison-group-by').value,personal=group!=='activity',rows=data.rows || [],identity=personal?['Técnico / técnico','Actividad','Unidad']:['Actividad','Unidad'];
  if(!rows.length)return empty('Ninguna actividad tiene registros en estos períodos y filtros.','Sin producción para comparar');
  const header=`<thead><tr class="table-group"><th colspan="${identity.length}" scope="colgroup">DESGLOSE DEL INFORME</th><th colspan="4" scope="colgroup">PRODUCTIVIDAD · B − A</th><th colspan="4" scope="colgroup">CALIDAD DE LAS REVISIONES</th><th rowspan="2" scope="col">Estado de producción</th></tr><tr>${identity.map((h)=>`<th scope="col">${h}</th>`).join('')}<th scope="col">Cantidad A<br><small>Referencia</small></th><th scope="col">Cantidad B<br><small>Comparado</small></th><th scope="col">Variación<br>absoluta</th><th scope="col">Crecimiento<br>(B − A) / A</th><th scope="col">Aprobación<br>A / B</th><th scope="col">Rechazo A<br><small>No aptas / evaluadas</small></th><th scope="col">Rechazo B<br><small>No aptas / evaluadas</small></th><th scope="col">Cambio rechazo<br><small>B − A · puntos porcentuales</small></th></tr></thead>`;
  const body=rows.map((row)=>{const rejectionDelta=row.rejection_rate_delta_pp ?? (row.rejection_rate_a!==null && row.rejection_rate_a!==undefined && row.rejection_rate_b!==null && row.rejection_rate_b!==undefined?row.rejection_rate_b-row.rejection_rate_a:null),cells=[];
    if(personal)cells.push(personCell(row.responsible_name,row.responsible_username));
    cells.push(`<strong>${escapeHtml(row.activity_name || 'Actividades del alcance')}</strong>${row.activity_ids?.length>1?`<small>${fmt(row.activity_ids.length)} actividades con la misma unidad</small>`:''}`,escapeHtml(row.unit),`<strong>${fmt(row.a)}</strong>`,`<strong>${fmt(row.b)}</strong>${sparkline(row.trend_b,row.unit)}`,`<strong>${escapeHtml(signed(row.delta))}</strong>`,escapeHtml(variation(row.percent,row.percent_state)),`${percent(row.approval_rate_a)} / ${percent(row.approval_rate_b)}`,`${percent(row.rejection_rate_a)}${row.evaluated_a?`<small>${fmt(row.rejected_a)} / ${fmt(row.evaluated_a)}</small>`:''}`,`${percent(row.rejection_rate_b)}${row.evaluated_b?`<small>${fmt(row.rejected_b)} / ${fmt(row.evaluated_b)}</small>`:''}`,rejectionDelta===null?'—':`${signed(rejectionDelta)} pp`,comparisonStatus(row));
    const deltaIndex=identity.length+2,percentIndex=identity.length+3,rejectionIndex=identity.length+7;
    return `<tr data-comparison-unit="${escapeHtml(row.unit)}" data-unit="${escapeHtml(row.unit)}" data-responsible="${escapeHtml(row.responsible_id ?? '')}" data-activity="${escapeHtml(row.activity_id ?? '')}">${cells.map((cell,i)=>`<td${i===deltaIndex || i===percentIndex?` class="delta-cell ${deltaClass(row.delta)}"`:i===rejectionIndex?` class="delta-cell ${deltaClass(rejectionDelta,true)}"`:''}>${cell}</td>`).join('')}</tr>`;
  }).join('');
  const units=[...new Set([...Object.keys(data.period_a.totals_by_unit || {}),...Object.keys(data.period_b.totals_by_unit || {})])];
  const totals=units.map((unit)=>{const a=data.period_a.totals_by_unit?.[unit] || 0,b=data.period_b.totals_by_unit?.[unit] || 0,delta=b-a,pct=a?(b-a)/a*100:b?null:0;return `<tr class="table-total"><th scope="row" colspan="${identity.length-1}">TOTAL · ${escapeHtml(unit)}</th><td>${escapeHtml(unit)}</td><td>${fmt(a)}</td><td>${fmt(b)}</td><td class="delta-cell ${deltaClass(delta)}">${signed(delta)}</td><td class="delta-cell ${deltaClass(delta)}">${variation(pct,a===0 && b>0?'sin_base':'')}</td><td colspan="5">Total de cantidad en esta unidad · tasas detalladas por fila</td></tr>`;}).join('');
  return `<div class="table-wrap" tabindex="0" aria-label="Tabla comparativa desplazable"><table class="data-table analytics-table comparison-data-table">${header}<tbody>${body}</tbody><tfoot>${totals}</tfoot></table></div>`;
}
async function loadComparison(){
  updateFilterSummary();
  if(isVisitor())$('comparison-group-by').value='activity';
  $('comparison-group-by').querySelectorAll('option').forEach((option)=>{option.disabled=isVisitor() && option.value!=='activity';});
  const query=comparisonQuery(),data=await api(`/api/comparativas?${query}`),summary=data.summary;S.comparisonQuery=query.toString();clearError($('comparison-error'));
  $('comparison-metrics').innerHTML=metricCards([['Registros en referencia A',summary.records_a,'Eventos de actividad, no cantidades'],['Registros en comparado B',summary.records_b,'Eventos de actividad, no medidores únicos'],['Variación de registros',signed(summary.delta_records),'Registros de B − registros de A',deltaClass(summary.delta_records)],['Crecimiento de registros',variation(summary.percent_records,summary.percent_state),'(B − A) / A × 100']]);
  $('comparison-periods').textContent=`A · referencia: ${prettyDate(data.period_a.from)} — ${prettyDate(data.period_a.to)} (${fmt(data.period_a.days)} días). B · comparado: ${prettyDate(data.period_b.from)} — ${prettyDate(data.period_b.to)} (${fmt(data.period_b.days)} días). ${data.period_a.days!==data.period_b.days?'Los períodos tienen distinta duración; se comparan cantidades brutas, sin normalizar por día.':'Ambos períodos tienen la misma duración.'}`;
  const group=data.group_by || $('comparison-group-by').value;$('comparison-table-title').textContent=({activity:'Comparación por actividad y unidad',technician:'Comparación por técnico y unidad',technician_activity:'Comparación por técnico y actividad'})[group] || 'Comparación de producción';
  $('comparison-table').innerHTML=comparisonTable(data);
  const seriesTable=(rows)=>table(['Intervalo','Registros','Cantidades por unidad'],rows.map((row)=>[escapeHtml(row.label),fmt(row.records),Object.entries(row.totals_by_unit || {}).map(([unit,value])=>`${fmt(value)} ${escapeHtml(unit)}`).join('<br>') || '—']));
  $('comparison-series-a').innerHTML=seriesTable(data.series_a || []);$('comparison-series-b').innerHTML=seriesTable(data.series_b || []);
  S.comparison=data;comparisonChart(data);
  for(const format of ['xlsx','pdf'])$(`comparison-export-${format}`).href=`/api/comparativas.${format}?${query}`;
  refreshTemplateStatus();
}
const TEMPLATE_IDS=['comparison-a-from','comparison-a-to','comparison-b-from','comparison-b-to','comparison-granularity','comparison-group-by','filter-activity','filter-responsible','filter-sap','filter-voltage','filter-brand','filter-model','filter-condition'];
function templateKey(){return `lab-report-template-v1-${S.user?.id}`;}
function readReportTemplate(){try{return JSON.parse(localStorage.getItem(templateKey()) || 'null');}catch(_){return null;}}
function refreshTemplateStatus(){const saved=readReportTemplate();$('comparison-load-template').disabled=!saved;$('comparison-template-status').textContent=saved?`Plantilla guardada ${prettyTime(saved.saved_at)} · solo rangos y filtros en este navegador.`:'La plantilla guarda rangos y filtros en este navegador.';}
function saveReportTemplate(){comparisonQuery();const values=Object.fromEntries(TEMPLATE_IDS.filter((id)=>id!=='filter-responsible' || isManager()).map((id)=>[id,$(id).value]));try{localStorage.setItem(templateKey(),JSON.stringify({version:1,saved_at:new Date().toISOString(),values}));refreshTemplateStatus();toast('Plantilla de rangos y filtros guardada.');}catch(_){throw new Error('Este navegador no permite guardar la plantilla. Los registros no se modificaron.');}}
async function loadReportTemplate(){const saved=readReportTemplate();if(!saved?.values)return toast('Todavía no tienes una plantilla guardada.','warning');for(const id of TEMPLATE_IDS){if(id==='filter-responsible'&&!isManager())continue;if(id==='comparison-group-by'&&isVisitor()){$(id).value='activity';continue;}if(typeof saved.values[id]==='string')$(id).value=saved.values[id];}await loadComparison();toast('Plantilla aplicada al informe.');}

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
function recordRows(records, actions=true) {return records.map((r)=>[escapeHtml(prettyDate(r.work_date)),`<strong>${escapeHtml(r.activity_name)}</strong><small>Versión ${escapeHtml(r.activity_version)}</small>`,recordSummary(r),`${fmt(r.quantity)}<small>${escapeHtml(r.unit)}</small>`,personCell(r.responsible_name,r.responsible_username,r.responsible_id),badge(r.state==='anulado'?'Anulado':'Válido',r.state==='anulado'?'danger':'good'),actions?`<button class="mini-button" data-event="${r.id}" data-action="detail">Ver</button>${r.state==='anulado'?isManager()?`<button class="mini-button" data-event="${r.id}" data-action="restore">Restaurar</button>`:'':`<button class="mini-button" data-event="${r.id}" data-action="edit">Corregir</button><button class="mini-button danger-text" data-event="${r.id}" data-action="void">Anular</button>`}`:'']);}
async function loadRecords() {
  const owner=S.user.id;
  const q=filterQuery({meter:$('records-meter').value.trim(),state:$('records-state').value,page:S.page,page_size:20});
  const data=await api(`/api/eventos?${q}`);if(!S.user||S.user.id!==owner)return;S.records=data.records || [];S.page=data.page || 1;S.pages=data.pages || 1;
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
  openDialog('Corregir registro',`<form id="edit-record-form" class="dialog-form"><p class="muted">Se conservarán el registro anterior, el motivo y la persona que realiza esta corrección.</p><div class="form-grid two"><label>Fecha de trabajo<input id="edit-date" type="date" value="${escapeHtml(record.work_date)}" required></label><label>Cantidad<input id="edit-quantity" type="number" min="1" step="1" value="${record.quantity}" ${record.mode==='individual'?'readonly':''} required></label></div><div id="edit-fields" class="form-grid two">${fields.map((f)=>fieldHtml(f,record.data?.[f.key] ?? '','edit')).join('')}</div>${S.production&&S.phase>=2?`<label>Justificación de repetición (si corresponde)<input id="edit-duplicate-note" maxlength="1500" value="${escapeHtml(record.traceability?.duplicate_note||'')}"></label>`:''}<label>Motivo de la corrección<textarea id="edit-reason" required minlength="3" maxlength="500" rows="2"></textarea></label><div class="notice error hidden" id="edit-error" role="alert"></div><div class="dialog-actions"><button type="button" class="btn secondary" id="edit-cancel">Cancelar</button><button class="btn primary" type="submit">Guardar corrección</button></div></form>`,()=>{
    $('edit-cancel').onclick=closeDialog;
    $('edit-record-form').onsubmit=(event)=>{event.preventDefault();busy(event.submitter,async()=>{await api(`/api/eventos/${record.id}/corregir`,{work_date:$('edit-date').value,quantity:Number($('edit-quantity').value),data:readFields($('edit-fields')),reason:$('edit-reason').value.trim(),duplicate_note:$('edit-duplicate-note')?.value||''});closeDialog();toast('Corrección guardada con su historial.');await loadRecords();},$('edit-error'));};
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
  $('activities-grid').innerHTML=S.activities.map((a)=>`<article class="card activity-card"><div class="activity-header"><span class="activity-symbol" aria-hidden="true">${escapeHtml(a.illustration||(a.mode==='individual'?'⌕':a.mode==='recepcion'?'⇣':'◈'))}</span>${badge(a.active?'Habilitada':'Desactivada',a.active?'good':'muted')}</div><h2>${escapeHtml(a.name)}</h2><p>${escapeHtml(modeNames[a.mode] || a.mode)} · ${escapeHtml(a.unit)}</p><div class="activity-fields">${a.fields.slice(0,5).map((f)=>`<span class="field-pill">${escapeHtml(f.label || labels[f.key] || f.key)}</span>`).join('')}${a.fields.length>5?`<span class="field-pill">+${a.fields.length-5}</span>`:''}</div><div class="activity-footer"><span class="muted">Versión ${a.version}</span><button class="btn small secondary" data-edit-activity="${escapeHtml(a.id)}">Configurar →</button></div></article>`).join('');
}
function slug(label) {return String(label).normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,'_').replace(/^_+|_+$/g,'').replace(/^(?=\d)/,'campo_').slice(0,40);}
function editActivity(activity=null) {
  let draft=(activity?.fields || [{key:'descripcion',label:'Descripción del trabajo',type:'text',required:true},{key:'observaciones',label:'Observaciones',type:'text',required:false}]).map((f)=>({...f}));
  openDialog(activity?'Configurar actividad':'Crear actividad',`<form id="activity-form" class="dialog-form"><div class="notice soft">Los cambios se aplican a nuevas capturas. Los registros anteriores conservan su versión.</div><label>Nombre de la actividad<input id="activity-name" required maxlength="120" value="${escapeHtml(activity?.name || '')}" placeholder="Nombre que verán los técnicos"></label><div class="form-grid two"><label>Forma de registro<select id="activity-mode">${options([{value:'lote',label:'Por cantidad / lote'},{value:'individual',label:'Por medidor individual'},{value:'recepcion',label:'Recepción con entregas'}],activity?.mode || 'lote',null)}</select></label><label>Unidad de producción<input id="activity-unit" required maxlength="40" value="${escapeHtml(activity?.unit || 'medidores')}" placeholder="Medidores, sellos, revisiones…"></label></div>${S.production&&S.phase>=2?`<label>Ilustración de la actividad<select id="activity-illustration">${options(['◈','⌕','⇣','⚙','✓'],activity?.illustration||'◈',null)}</select></label>`:''}<label class="checkbox-label"><input id="activity-active" type="checkbox" ${activity?.active===false?'':'checked'}> Actividad habilitada para nuevas capturas</label><div class="card-heading"><h3>Datos que solicitará el formulario</h3><button id="add-field" type="button" class="btn small secondary">＋ Añadir dato</button></div><p class="muted small-text">La fecha, la persona responsable y la cantidad ya se incluyen automáticamente.</p><div id="field-builder" class="field-builder"></div><div id="activity-error" class="notice error hidden" role="alert"></div><div class="dialog-actions"><button id="activity-cancel" type="button" class="btn secondary">Cancelar</button><button type="submit" class="btn primary">${activity?'Guardar nueva versión':'Crear actividad'}</button></div></form>`,()=>{
    const readDraft=()=>[...$('field-builder').querySelectorAll('.field-editor')].map((row)=>{const base=draft.find((field)=>field.key && field.key===row.dataset.key) || {};const field={...base,key:row.dataset.key || slug(row.querySelector('[data-part="label"]').value),label:row.querySelector('[data-part="label"]').value.trim(),type:row.querySelector('[data-part="type"]').value,required:row.querySelector('[data-part="required"]').checked,options:row.querySelector('[data-part="options"]').value.split(',').map((x)=>x.trim()).filter(Boolean)};const control=row.querySelector('[data-part=source]');const source=control?control.value:base.source;if(field.type==='select'&&source)field.source=source;else delete field.source;return field;});
    const draw=()=>{$('field-builder').innerHTML=draft.map((f,i)=>`<div class="field-editor" data-key="${escapeHtml(f.key || '')}"><div class="field-editor-header"><strong>Dato ${i+1}</strong><button type="button" class="text-button danger-text" data-remove-field="${i}">Quitar</button></div><div class="form-grid two"><label>Nombre del dato<input data-part="label" required maxlength="80" value="${escapeHtml(f.label || '')}"></label><label>Tipo<select data-part="type">${options([{value:'text',label:'Texto'},{value:'number',label:'Número'},{value:'date',label:'Fecha'},{value:'select',label:'Lista de opciones'},{value:'checkbox',label:'Casilla sí / no'}],f.type || 'text',null)}</select></label></div>${S.production&&S.phase>=2?`<label class="${f.type==='select'?'':'hidden'}" data-source-wrap>Origen de opciones<select data-part="source">${options([{value:'',label:'Lista propia de esta actividad'},...['marcas','voltajes','condiciones','modelos','piezas','puestos','tipos'].map(value=>({value,label:'Catálogo maestro: '+value}))],f.source||'',null)}</select></label>`:''}<label class="${f.type==='select'?'':'hidden'}" data-options-wrap>Opciones, separadas por comas<input data-part="options" value="${escapeHtml((f.options || []).join(', '))}" placeholder="Opción uno, opción dos"></label><label class="checkbox-label"><input data-part="required" type="checkbox" ${f.required?'checked':''}> Obligatorio</label></div>`).join('');};
    draw();$('add-field').onclick=()=>{draft=readDraft();if(draft.length>=24)return toast('Puedes definir hasta 24 datos por actividad.','warning');draft.push({label:'',type:'text',required:false,options:[]});draw();};
    $('field-builder').onclick=(event)=>{const button=event.target.closest('[data-remove-field]');if(!button)return;draft=readDraft();draft.splice(Number(button.dataset.removeField),1);draw();};
    $('field-builder').onchange=(event)=>{if(event.target.matches('[data-part="type"]')){event.target.closest('.field-editor').querySelector('[data-options-wrap]').classList.toggle('hidden',event.target.value!=='select');event.target.closest('.field-editor').querySelector('[data-source-wrap]')?.classList.toggle('hidden',event.target.value!=='select');}};
    $('activity-mode').onchange=()=>{if(!activity && $('activity-mode').value==='individual' && !readDraft().some((f)=>f.key==='serie')){draft=readDraft();draft.unshift({key:'serie',label:'Serie del medidor',type:'text',required:true});draw();}};
    $('activity-cancel').onclick=closeDialog;
    $('activity-form').onsubmit=(event)=>{event.preventDefault();busy(event.submitter,async()=>{const fields=readDraft();if(new Set(fields.map((f)=>f.key)).size!==fields.length)throw new Error('Cada dato debe tener un nombre diferente.');if(fields.some((f)=>!f.key || !f.label || f.type==='select'&&!f.options.length&&!f.source))throw new Error('Completa los nombres y las opciones de cada lista.');const payload={name:$('activity-name').value.trim(),mode:$('activity-mode').value,unit:$('activity-unit').value.trim(),active:$('activity-active').checked,fields};if(activity)payload.id=activity.id;if($('activity-illustration'))payload.illustration=$('activity-illustration').value;await api('/api/actividades',payload);await loadReferences();closeDialog();toast(activity?'Nueva versión guardada. El histórico se conserva.':'Actividad creada. Puedes asignarla a los técnicos.');await loadActivities();},$('activity-error'));};
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
  $('import-preview').innerHTML=`<div class="card-heading"><div><h2>Resultado de la validación</h2><p>${fmt(data.rows_count)} filas leídas · ${fmt(data.valid_count)} válidas</p></div><span class="step-chip">02 · CONFIRMAR</span></div>${data.already_imported?'<div class="notice soft">Este archivo ya fue importado. Repetir la carga no añadirá registros.</div>':''}${errors.length?`<div class="notice error"><strong>${fmt(errors.length)} incidencias impiden confirmar la carga.</strong><p>Corrige el archivo y vuelve a revisarlo.</p></div>${table(['Fila','Error'],errors.map((e)=>[escapeHtml(e.row),escapeHtml(e.message)]))}`:'<div class="notice success">Las filas superaron la validación inicial.</div>'}${table(['Técnico','Cantidad atribuida'],(data.summary || []).map((r)=>[escapeHtml(r.responsible_name),fmt(r.quantity)]),'No hay cantidades listas para confirmar.')}${warnings.length?`<div class="notice warning"><strong>Advertencias que requieren revisión</strong><ul>${warnings.slice(0,20).map((w)=>`<li>Fila ${escapeHtml(w.row)}: ${escapeHtml(w.message)}</li>`).join('')}</ul></div><label class="checkbox-label"><input id="import-confirm-warnings" type="checkbox"> He revisado las advertencias y confirmo los reingresos indicados.</label>`:''}<div class="dialog-actions"><button id="confirm-import" class="btn primary" ${errors.length || !data.valid_count || data.already_imported?'disabled':''}>Confirmar ${fmt(data.valid_count)} registros</button></div><div id="import-confirm-error" class="notice error hidden" role="alert"></div>`;
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
  const data=await api(`/api/ordenes?${query}`);S.receiptsQuery=query.toString();S.orders=data.orders || [];S.receiptSummary=data.summary || {};renderReceiptOrders();
}
function renderReceiptOrders() {
  const orders=S.orders || [],scope=$('receipts-state').value,summary=S.receiptSummary || {};
  $('receipts-metrics').innerHTML=metricCards([
    ['Cantidad esperada',summary.expected_total ?? orders.filter((o)=>o.expected!==null).reduce((sum,o)=>sum+o.expected,0),'Medidores · órdenes con esperado confirmado'],
    ['Cantidad recibida',summary.received_total ?? orders.reduce((sum,o)=>sum+o.received,0),'Medidores · todas las entregas acumuladas'],
    ['Cantidad pendiente',summary.pending_total ?? orders.reduce((sum,o)=>sum+(o.pending || 0),0),'Medidores · solo esperado confirmado'],
    ['Avance de recepción',percent(summary.fulfillment_pct),'Recibido hasta el esperado / esperado confirmado'],
    ['Órdenes con alertas',orders.filter((o)=>o.signal==='rojo' && o.state!=='cerrada').length,'Vencimiento, exceso o conflicto de proceso'],
    ['Órdenes por confirmar',summary.unknown_orders ?? orders.filter((o)=>o.expected===null).length,'Sin cantidad esperada; no se asume saldo cero']]);
  $('receipts-scope-note').textContent=`${receiptContext()}. ${fmt(orders.length)} órdenes en este alcance; ${fmt(orders.filter((o)=>o.state==='cerrada').length)} cerradas. Los contadores resumen todos los estados; el selector inferior solo cambia las filas. El avance limita cada orden al esperado; los excesos se muestran en su fila.`;
  const visible=orders.filter((o)=>scope==='all' || scope==='active' && o.state!=='cerrada' || scope==='overdue' && o.signal==='rojo' && o.state!=='cerrada' || scope==='closed' && o.state==='cerrada' || scope==='complete' && o.state==='completa');
  $('receipts-table').innerHTML=table(['Proceso / orden','Código SAP','Cantidad esperada','Cantidad recibida','Avance','Pendiente / %','Seguimiento y fecha','Entregas','Acciones'],visible.map((o)=>[
    `<strong class="mono">${escapeHtml(o.process)}</strong><small>${escapeHtml(o.order_number)}</small>${o.provider?`<small>Proveedor: ${escapeHtml(o.provider)}</small>`:''}`,escapeHtml(o.sap),o.expected===null?'Por confirmar':fmt(o.expected),`${fmt(o.received)}${o.own_received===undefined?'':`<small>Tu aporte: ${fmt(o.own_received)}</small>`}`,orderProgress(o),
    o.pending===null?'Por confirmar':`${fmt(o.pending)}<small>${o.expected?percent(o.pending/o.expected*100):'Sin base'} pendiente</small>${o.excess?`<small class="danger-text">Exceso: ${fmt(o.excess)}</small>`:''}`,
    `${signalBadge(o.signal,orderStateLabel(o))}${o.due_date?`<small>Fecha límite: ${escapeHtml(prettyDate(o.due_date))}</small>`:''}`,fmt(o.deliveries),
    `<button class="mini-button" data-order-detail="${o.id}">Ver detalle</button>${isManager() && o.state!=='cerrada'?`<button class="mini-button" data-order-edit="${o.id}">Editar orden</button>`:''}${o.state!=='cerrada' && activeActivities().some((a)=>a.id==='recepcion')?`<button class="mini-button" data-order-delivery="${o.id}">＋ Entrega</button>`:''}${isManager() && o.state==='completa' && !o.process_conflict && !o.excess?`<button class="mini-button" data-order-close="${o.id}">Cerrar lote</button>`:''}${isManager() && o.state==='cerrada'?`<button class="mini-button" data-order-reopen="${o.id}">Reabrir</button>`:''}`]),'No hay órdenes para este estado. Puedes crear una orden o registrar la primera entrega.');
  $('receipts-table').querySelector('table')?.classList.add('analytics-table','receipts-analysis-table');
}
function orderStateLabel(order) {return order.state==='cerrada'?'Cerrada':order.process_conflict?'Proceso duplicado: revisar':order.excess?'Exceso recibido':order.overdue?'Vencida':({completa:'Completa, lista para cerrar',pendiente:'Pendiente',por_confirmar:'Cantidad por confirmar'}[order.state] || order.state);}
function createOrder() {
  openDialog('Crear orden de recepción',`<form id="order-form" class="dialog-form"><div class="form-grid two"><label>Número de proceso único<input id="order-process" required maxlength="120" autocomplete="off"></label><label>Número de orden<input id="order-number" required maxlength="120"></label><label>Código SAP<input id="order-sap" required maxlength="60" list="sap-list"></label><label>Cantidad esperada<input id="order-expected" type="number" required min="1" max="1000000" step="1"></label>${S.production&&S.phase>=2?'<label>Proveedor<input id="order-provider" maxlength="150"></label>':''}<label>Fecha límite<input id="order-due" type="date"></label><label>Observaciones<textarea id="order-notes" maxlength="1500" rows="2"></textarea></label></div><div id="order-error" class="notice error hidden" role="alert"></div><div class="dialog-actions"><button id="order-cancel" type="button" class="btn secondary">Cancelar</button><button type="submit" class="btn primary">Crear orden</button></div></form>`,()=>{
    $('order-cancel').onclick=closeDialog;$('order-form').onsubmit=(event)=>{event.preventDefault();busy(event.submitter,async()=>{await api('/api/ordenes',{process:$('order-process').value.trim(),order_number:$('order-number').value.trim(),sap:$('order-sap').value.trim(),expected:Number($('order-expected').value),due_date:$('order-due').value,notes:$('order-notes').value.trim(),provider:$('order-provider')?.value||''});closeDialog();toast('Orden creada. Cada entrega conservará su trazabilidad.');await loadReceipts();},$('order-error'));};
  });
}
function editOrder(id) {
  const order=(S.orders || []).find((o)=>String(o.id)===String(id));if(!order)return;
  openDialog('Actualizar seguimiento de la orden',`<form id="order-edit-form" class="dialog-form"><p class="muted">Orden ${escapeHtml(order.order_number)} · SAP ${escapeHtml(order.sap)}. Las entregas y sus responsables se conservan.</p><div class="form-grid two"><label>Número de proceso único<input id="order-edit-process" required maxlength="160" value="${escapeHtml(order.process)}"></label><label>Cantidad esperada<input id="order-edit-expected" type="number" min="0" max="1000000" step="1" value="${order.expected===null?'':order.expected}"></label>${S.production&&S.phase>=2?`<label>Proveedor<input id="order-edit-provider" value="${escapeHtml(order.provider||'')}" maxlength="150"></label>`:''}<label>Fecha límite<input id="order-edit-due" type="date" value="${escapeHtml(order.due_date || '')}"></label><label>Observaciones<textarea id="order-edit-notes" rows="2" maxlength="1500">${escapeHtml(order.notes || '')}</textarea></label></div><label>Motivo del cambio<textarea id="order-edit-reason" required minlength="3" maxlength="1500" rows="2"></textarea></label><div id="order-edit-error" class="notice error hidden" role="alert"></div><div class="dialog-actions"><button id="order-edit-cancel" class="btn secondary" type="button">Cancelar</button><button class="btn primary" type="submit">Guardar seguimiento</button></div></form>`,()=>{
    $('order-edit-cancel').onclick=closeDialog;$('order-edit-form').onsubmit=(event)=>{event.preventDefault();busy(event.submitter,async()=>{await api('/api/ordenes',{id:order.id,process:$('order-edit-process').value.trim(),expected:$('order-edit-expected').value===''?null:Number($('order-edit-expected').value),due_date:$('order-edit-due').value,notes:$('order-edit-notes').value.trim(),provider:$('order-edit-provider')?.value||'',reason:$('order-edit-reason').value.trim()});closeDialog();toast('Seguimiento actualizado con su motivo en auditoría.');await loadReceipts();},$('order-edit-error'));};
  });
}
async function showOrderDetail(id) {
  const data=await api(`/api/ordenes/${id}`),order=data.order;
  openDialog(`Proceso ${order.process}`,`<div class="detail-title">${signalBadge(order.signal,orderStateLabel(order))}</div><dl class="detail-list"><dt>Orden</dt><dd>${escapeHtml(order.order_number)}</dd>${S.production&&S.phase>=2?`<dt>Proveedor</dt><dd>${escapeHtml(order.provider||'Pendiente de indicar')}</dd>`:''}<dt>Código SAP</dt><dd>${escapeHtml(order.sap)}</dd><dt>Recibido / esperado</dt><dd>${fmt(order.received)} / ${order.expected===null?'Por confirmar':fmt(order.expected)}</dd><dt>Pendiente</dt><dd>${order.pending===null?'Por confirmar':fmt(order.pending)}</dd><dt>Fecha límite</dt><dd>${escapeHtml(prettyDate(order.due_date))}</dd><dt>Observaciones</dt><dd>${escapeHtml(order.notes || '—')}</dd></dl><h3>Entregas registradas</h3>${table(['Fecha','Cantidad','Responsable','Registrado por','Estado'],(data.deliveries || []).map((r)=>[escapeHtml(prettyDate(r.work_date)),fmt(r.quantity),escapeHtml(r.responsible_name || '—'),escapeHtml(r.recorded_by_name || '—'),badge(r.state==='anulado'?'Anulada':'Válida',r.state==='anulado'?'danger':'good')]),'La primera entrega aparecerá aquí.')}${data.certificates?.length?`<h3>Actas de cierre conservadas</h3>${table(['Acta / fecha','Estado','Huella SHA-256','Descargas'],data.certificates.map((c)=>[`${escapeHtml(c.number)}<small>${escapeHtml(prettyTime(c.created_at))}</small>`,badge(c.current?'Vigente':'Histórica',c.current?'good':'muted'),`<span class="hash-value">${escapeHtml(c.hash)}</span>`,`<a class="btn small secondary" href="/api/ordenes/${order.id}/acta.pdf?certificate_id=${encodeURIComponent(c.id)}">PDF</a> <a class="btn small secondary" href="/api/ordenes/${order.id}/acta.json?certificate_id=${encodeURIComponent(c.id)}">JSON</a>`]))}`:''}<div class="dialog-actions">${order.state==='cerrada'?`<a href="/api/ordenes/${order.id}/acta.pdf" class="btn primary">Descargar acta PDF</a><button class="btn secondary" data-order-certificate="${order.id}">Ver sello del acta</button>`:`${activeActivities().some((a)=>a.id==='recepcion')?`<button class="btn secondary" data-order-delivery="${order.id}">Registrar entrega</button>`:''}${isManager() && order.state==='completa' && !order.process_conflict && !order.excess?`<button class="btn primary" data-order-close="${order.id}">Cerrar lote</button>`:''}`}</div>`);
}
async function registerOrderDelivery(id) {
  const order=(S.orders || []).find((o)=>String(o.id)===String(id)) || (await api(`/api/ordenes/${id}`)).order;
  if(S.production&&S.phase>=2)return LabPhaseTwo.delivery(order);
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
function renderGoals(goals, compact=false) { const list=compact?goals.slice(0,5):goals;return table(['Técnico','Actividad','Período','Producción / meta','Avance','Estado'],list.map((g)=>[personCell(g.responsible_name || 'Equipo','',g.responsible_id),`<strong>${escapeHtml(g.activity_name)}</strong><small>${escapeHtml(g.unit)}</small>`,`${escapeHtml(prettyDate(g.start_date))}<small>${escapeHtml(prettyDate(g.end_date))}</small>`,`${fmt(g.produced)} / ${fmt(g.target)}`,progress(g.pct),badge(String(g.state || '').replaceAll('_',' '),g.pct>=100?'good':g.state==='vencida'?'danger':'soft')]),'Las metas aparecerán cuando el supervisor las asigne.'); }
async function loadGoals() { const data=await api('/api/metas');S.goals=data.goals || [];$('goals-table').innerHTML=renderGoals(S.goals);$('goals-hint').textContent=isManager()?'Cada avance corresponde a una actividad y unidad.':'Aquí encontrarás las metas asignadas a tu cuenta.';if(!$('goal-from').value)$('goal-from').value=today();if(!$('goal-to').value)$('goal-to').value=today();updateGoalUnit(); }
function updateGoalUnit() {let wrap=$('goal-unit-wrap');if(!wrap){wrap=document.createElement('label');wrap.id='goal-unit-wrap';wrap.innerHTML='Unidad<select id="goal-unit"><option value="medidores">Medidores</option><option value="sellos">Sellos</option></select>';$('goal-form').querySelector('.form-grid').insertBefore(wrap,$('goal-form').querySelector('.field-action'));}wrap.classList.toggle('hidden',$('goal-activity').value!=='asignacion');}

async function loadUsers() { if(S.production&&S.phase>=2)return LabPhaseTwo.loadPeople(); const data=await api('/api/usuarios');S.users=data.users || []; $('users-table').innerHTML=table(['Técnico','Usuario','Perfil','Actividades','Estado','Acciones'],S.users.map((u)=>[personCell(u.name,u.username,u.id),escapeHtml(u.username),escapeHtml(roleNames[u.role] || u.role),escapeHtml((u.activity_ids || []).map((id)=>S.activities.find((a)=>a.id===id)?.name || id).join(' · ') || 'Sin actividades'),badge(u.active?'Activo':'Inactivo',u.active?'good':'muted'),`${S.user.role==='administrador' || u.role==='tecnico'?`<button class="mini-button" data-edit-user="${u.id}">Editar</button>`:''}${u.role==='tecnico' || S.production && S.user.role==='administrador' && !u.is_master && u.id!==S.user.id?`<button class="mini-button" data-reset-user="${u.id}">Restablecer acceso</button>`:''}`])); if(S.production)LabFoundation.renderCards(S.users); }
function editUser(user=null) {
  if(S.production)return LabFoundation.editUser(user);
  const roles=S.user.role==='administrador'?['tecnico','supervisor','administrador','visitante']:['tecnico'];
  openDialog(user?'Editar técnico':'Agregar técnico',`<form id="user-form" class="dialog-form"><div class="form-grid two"><label>Nombre completo<input id="user-name" required maxlength="90" value="${escapeHtml(user?.name || '')}"></label><label>Usuario / código de empleado<input id="user-username" required maxlength="35" value="${escapeHtml(user?.username || '')}" ${user?'readonly':''} autocomplete="off"></label></div>${user?`<p>Perfil: <strong>${escapeHtml(roleNames[user.role] || user.role)}</strong></p>`:`<label>Perfil<select id="user-role">${options(roles.map((r)=>({value:r,label:roleNames[r]})),'tecnico',null)}</select></label><div id="user-password-wrap" class="hidden"><label>Contraseña inicial propia<input id="user-password" type="password" minlength="10" maxlength="128" autocomplete="new-password"></label></div><div id="user-code-hint" class="notice soft">Para técnicos, la primera contraseña será su mismo código de empleado. El cambio posterior es opcional.</div>`}<label class="checkbox-label"><input id="user-active" type="checkbox" ${user?.active===false?'':'checked'} ${user?.id===S.user.id?'disabled':''}> Cuenta activa</label><fieldset><legend>Actividades habilitadas</legend><p class="muted small-text">La persona podrá cambiar entre estas actividades y fijar una durante la jornada.</p><div class="user-activity-checks">${S.activities.filter((a)=>a.active).map((a)=>`<label class="checkbox-label"><input type="checkbox" data-user-activity="${escapeHtml(a.id)}" ${(user?.activity_ids || []).includes(a.id)?'checked':''}>${escapeHtml(a.name)}</label>`).join('')}</div><button type="button" id="select-all-activities" class="text-button">Seleccionar todas</button></fieldset><div id="user-error" class="notice error hidden" role="alert"></div><div class="dialog-actions"><button id="user-cancel" type="button" class="btn secondary">Cancelar</button><button type="submit" class="btn primary">${user?'Guardar cambios':'Crear acceso'}</button></div></form>`,()=>{
    $('user-cancel').onclick=closeDialog;$('select-all-activities').onclick=()=>document.querySelectorAll('[data-user-activity]').forEach((n)=>n.checked=true);
    if($('user-role'))$('user-role').onchange=()=>{const nontech=$('user-role').value!=='tecnico';$('user-password-wrap').classList.toggle('hidden',!nontech);$('user-password').required=nontech;$('user-code-hint').classList.toggle('hidden',nontech);};
    $('user-form').onsubmit=(event)=>{event.preventDefault();busy(event.submitter,async()=>{const assigned=[...document.querySelectorAll('[data-user-activity]:checked')].map((n)=>n.dataset.userActivity);const payload={name:$('user-name').value.trim(),active:$('user-active').checked,activity_ids:assigned};if(user)await api(`/api/usuarios/${user.id}/actualizar`,payload);else {payload.username=$('user-username').value.trim();payload.role=$('user-role').value;if(payload.role!=='tecnico')payload.password=$('user-password').value;await api('/api/usuarios',payload);}await loadReferences();closeDialog();toast(user?'Técnico actualizado.':'Acceso creado.');await loadUsers();},$('user-error'));};
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
  $('password-new').minLength=S.production?10:S.user.role==='tecnico'?4:10;
}

function bindEvents() {
  let resizeTimer;window.addEventListener('resize',()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>{if(!S.user)return;const visible=$(`view-${S.view}`);for(const [key,chart] of Object.entries(S.charts)){const node=$(`chart-${key}`);if(node && visible?.contains(node))chart.redraw?.();}},180);});
  const tooltip=$('chart-tooltip');
  function showChartTooltip(target,event){const text=target.dataset.chartTooltip;if(!text)return;tooltip.textContent=text;tooltip.classList.remove('hidden');const rect=target.getBoundingClientRect(),x=event?.clientX ?? rect.left+rect.width/2,y=event?.clientY ?? rect.top;tooltip.style.left=`${Math.max(8,Math.min(window.innerWidth-tooltip.offsetWidth-8,x+12))}px`;tooltip.style.top=`${Math.max(8,Math.min(window.innerHeight-tooltip.offsetHeight-8,y-tooltip.offsetHeight-12))}px`;}
  document.addEventListener('pointerover',(event)=>{const target=event.target.closest?.('[data-chart-tooltip]');if(target)showChartTooltip(target,event);});
  document.addEventListener('pointermove',(event)=>{const target=event.target.closest?.('[data-chart-tooltip]');if(target)showChartTooltip(target,event);});
  document.addEventListener('pointerout',(event)=>{if(event.target.closest?.('[data-chart-tooltip]') && !event.relatedTarget?.closest?.('[data-chart-tooltip]'))tooltip.classList.add('hidden');});
  document.addEventListener('focusin',(event)=>{const target=event.target.closest?.('[data-chart-tooltip]');if(target)showChartTooltip(target);});
  document.addEventListener('focusout',(event)=>{if(event.target.closest?.('[data-chart-tooltip]'))tooltip.classList.add('hidden');});
  document.addEventListener('keydown',(event)=>{if(event.key==='Escape')tooltip.classList.add('hidden');});
  document.addEventListener('click',(event)=>{
    if(event.target.closest('[data-guide-open]'))openQuickGuide();
    const view=event.target.closest('[data-view]');if(view)navigate(view.dataset.view);
    const chart=event.target.closest('[data-export-chart]');if(chart)exportChart(chart.dataset.exportChart,chart.dataset.format,chart);
    const activity=event.target.closest('[data-edit-activity]');if(activity)editActivity(S.activities.find((a)=>a.id===activity.dataset.editActivity));
    const edit=event.target.closest('[data-edit-user]');if(edit)editUser(S.users.find((u)=>String(u.id)===edit.dataset.editUser));
    const reset=event.target.closest('[data-reset-user]');if(reset){const user=S.users.find((u)=>String(u.id)===reset.dataset.resetUser);if(S.production)return LabFoundation.resetUser(user);confirmDialog('Restablecer acceso',`${user.name} volverá a acceder con su código como usuario y contraseña. Sus sesiones se cerrarán y su historial se conservará.`,async()=>{await api(`/api/usuarios/${user.id}/restablecer`,{});toast('Acceso restablecido al código de empleado.');},'Restablecer acceso');}
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
  $('logout-button').onclick=()=>busy($('logout-button'),async()=>{await api('/api/logout',{});S.user=null;S.csrf='';S.users=[];S.records=[];S.charts={};window.LabPhaseTwo?.clear();closeDialog();window.LabDetails?.close();$('users-table')?.replaceChildren();$('collaborator-cards')?.remove();$('base-profile-card')?.remove();$('profile-avatar-editor')?.remove();$('profile-details').replaceChildren();window.LabTables?.resetAll();$('password-form').reset();showAuth(false);});
  $('menu-toggle').onclick=()=>setMenu(!document.body.classList.contains('menu-open'));$('sidebar-backdrop').onclick=()=>setMenu(false);$('account-shortcut').onclick=()=>navigate('account');$('quick-capture').onclick=()=>navigate('capture');
  $('dialog-close').onclick=closeDialog;$('app-dialog').addEventListener('click',(e)=>{if(e.target===$('app-dialog')){const r=$('app-dialog').getBoundingClientRect();if(e.clientX<r.left || e.clientX>r.right || e.clientY<r.top || e.clientY>r.bottom)closeDialog();}});
  $('toggle-filters').onclick=()=>setFiltersCollapsed(!$('global-filters').classList.contains('filter-collapsed'));
  $('filter-form').onsubmit=(event)=>{event.preventDefault();if(!['comparison','receipts'].includes(S.view) && $('filter-from').value && $('filter-to').value && $('filter-from').value>$('filter-to').value)return toast('La fecha inicial debe ser anterior a la final.','warning');S.page=1;setFiltersCollapsed(true);navigate(S.view);};
  $('clear-filters').onclick=()=>{$('filter-form').reset();S.page=1;navigate(S.view);};
  $('capture-activity').onchange=()=>{renderCaptureFields();storePin();};$('pin-activity').onchange=storePin;
  $('capture-form').onsubmit=(event)=>{event.preventDefault();busy($('capture-submit'),()=>saveCapture(),$('capture-error'));};
  $('records-search').onclick=()=>{S.page=1;busy($('records-search'),loadRecords);};$('records-prev').onclick=()=>{if(S.page>1){S.page--;busy(null,loadRecords);}};$('records-next').onclick=()=>{if(S.page<S.pages){S.page++;busy(null,loadRecords);}};
  $('history-form').onsubmit=(event)=>{event.preventDefault();busy(event.submitter,searchHistory);};$('new-activity').onclick=()=>editActivity();$('new-user').onclick=()=>editUser();
  $('create-backup').onclick=()=>busy($('create-backup'),async()=>{if(S.production){await navigate('base');$('backup-now')?.focus();return;}const result=await api('/api/backup',{});toast(`Respaldo creado. ${result.message || 'Se guardó en la carpeta de respaldos de esta instalación.'}`);});
  $('import-activity').onchange=updateTemplateLinks;$('import-file').onchange=()=>{S.preview=null;$('import-preview').classList.add('hidden');};$('import-form').onsubmit=(event)=>{event.preventDefault();busy(event.submitter,previewImport,$('import-error'));};
  $('create-order').onclick=createOrder;$('receipts-state').onchange=renderReceiptOrders;
  $('dashboard-granularity').onchange=()=>busy(null,loadDashboard);$('dashboard-series').onchange=renderDashboardTrend;
  $('comparison-save-template').onclick=()=>busy($('comparison-save-template'),saveReportTemplate);$('comparison-load-template').onclick=()=>busy($('comparison-load-template'),loadReportTemplate,$('comparison-error'));
  $('quality-form').onsubmit=(event)=>{event.preventDefault();busy(event.submitter,loadQuality);};
  $('comparison-form').onsubmit=(event)=>{event.preventDefault();busy(event.submitter,loadComparison,$('comparison-error'));};
  $('new-receipt').onclick=async()=>{if(S.production&&S.phase>=2)return LabPhaseTwo.delivery({order_number:'',process:'',expected:'',provider:'',sap:'',pending:1});await navigate('capture');$('capture-activity').value='recepcion';renderCaptureFields();};
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
  setFiltersCollapsed(true);
  try {const me=await api('/api/me');S.production=Boolean(me.production_mode);S.demo=Boolean(me.demo);S.publicDemo=Boolean(me.public_demo);S.setup=Boolean(me.setup_required);S.lab=Boolean(me.lab_revision);S.phase=Number(me.delivered_phase)||0;S.installation=me.installation_id||'';if(me.logged)await enterApp(me);else showAuth();}
  catch(error){showAuth(false);showError($('auth-error'),error);}
}
init();
