/* Instalación local V33: acceso, perfil, administración y respaldo. */
(() => {
  'use strict';
  const id = name => document.getElementById(name);
  let statusData;
  const productionReady = () => {try{return typeof S!=='undefined' && S.production && S.user;}catch(_){return false;}};
  function enhance(){
    if(!productionReady())return;
    let nav=id('base-nav');if(!nav){nav=document.createElement('button');nav.id='base-nav';nav.dataset.view='base';nav.className='nav-item';nav.textContent='⚙ Instalación y respaldos';id('main-nav').append(nav);}
    const admin=S.user.role==='administrador';
    if(id('create-backup'))id('create-backup').classList.toggle('phase-hidden',!admin);
    document.querySelectorAll('#main-nav [data-view]').forEach(button=>{
      const allowed=['account','users',...(admin?['base','audit']:[])].includes(button.dataset.view);
      button.classList.toggle('phase-hidden',!allowed || button.dataset.view==='users'&&!isManager());
    });
    if(S.view==='account')profileForm().catch(error=>toast(error.message,'error'));
  }
  function note(message,kind='soft'){return `<p class="notice ${kind}" role="status">${escapeHtml(message)}</p>`;}
  function temporary(user,key){
    openDialog('Acceso temporal · una sola visualización',`<p>Usuario: <strong>${escapeHtml(user)}</strong></p><p>Clave temporal:</p><code class="temporary-key" tabindex="0">${escapeHtml(key)}</code><p>Entrégala al titular. En su primer ingreso deberá cambiarla y completar su perfil. La clave actual no se podrá consultar después.</p><button type="button" class="btn primary" id="temporary-close">Ya la guardé de forma segura</button>`,()=>id('temporary-close').onclick=closeDialog);
  }
  function editUser(user=null){
    const roles=S.user.role==='administrador'?['tecnico','supervisor','administrador','visitante']:['tecnico'];
    const supervisors=S.users.filter(person=>person.role==='supervisor' && person.active);
    openDialog(user?'Editar acceso':'Crear acceso',`<form id="base-user-form"><div class="form-grid two"><label>Nombre completo<input name="name" value="${escapeHtml(user?.name || '')}" required maxlength="90"></label><label>Puesto<input name="position" value="${escapeHtml(user?.position || '')}" required maxlength="150"></label>${user?'':`<label>Código de empleado / usuario<input name="username" required maxlength="35" autocomplete="off"></label><label>Perfil<select name="role">${roles.map(role=>`<option value="${role}">${escapeHtml(roleNames[role])}</option>`).join('')}</select></label>`}${S.user.role==='administrador'?`<label>Supervisor del técnico<select name="supervisor_id"><option value="">Sin asignar</option>${supervisors.map(person=>`<option value="${person.id}"${person.id===user?.supervisor_id?' selected':''}>${escapeHtml(person.name)}</option>`).join('')}</select></label>`:''}<label class="checkbox-label"><input name="active" type="checkbox"${user?.active===false?'':' checked'}> Acceso activo</label></div><p>La instalación genera una clave temporal nueva al crear el acceso. La asignación de actividades se habilitará en la fase 2.</p><div id="base-user-error" class="notice error hidden" role="alert"></div><button class="btn primary" type="submit">${user?'Guardar cambios':'Crear acceso'}</button></form>`,()=>{
      id('base-user-form').onsubmit=event=>{event.preventDefault();busy(event.submitter,async()=>{
        const form=event.target,values=Object.fromEntries(new FormData(form));values.active=form.elements.active.checked;values.activity_ids=user?.activity_ids || [];
        const result=await api(user?`/api/usuarios/${user.id}/actualizar`:'/api/usuarios',values);
        await loadReferences();closeDialog();await loadUsers();
        if(result.temporary_password)temporary(values.username,result.temporary_password);else toast('Acceso actualizado.');
      },id('base-user-error'));};
    });
  }
  function resetUser(person){
    openDialog('Restablecer acceso del técnico',`<p>Se creará una clave temporal nueva para <strong>${escapeHtml(person.name)}</strong>, se cerrarán sus sesiones y conservará su historial.</p><p>Después deberá cambiar esa clave.</p><div id="base-reset-error" class="notice error hidden" role="alert"></div><button id="base-reset-confirm" class="btn primary" type="button">Generar nueva clave temporal</button>`,()=>{
      id('base-reset-confirm').onclick=()=>busy(id('base-reset-confirm'),async()=>{const result=await api(`/api/usuarios/${person.id}/restablecer`,{});closeDialog();temporary(person.username,result.temporary_password);},id('base-reset-error'));
    });
  }
  function personCard(person){
    return `<article class="person-profile-card"><div class="person-profile-banner"><span data-avatar-host data-avatar-user-id="${person.id}" data-avatar-size="80"></span><div><small>${escapeHtml(roleNames[person.role] || person.role)}</small><h3>${escapeHtml(person.name)}</h3><p>${escapeHtml(person.position || 'Puesto pendiente de completar')}</p></div></div><dl><dt>Código de empleado / usuario</dt><dd>${escapeHtml(person.username)}</dd><dt>Acceso</dt><dd>${person.active===false?'Inactivo':'Activo'}</dd></dl><p class="person-profile-note">Ficha de identificación. Producción, metas, ranking y comparativas se incorporarán en la fase 3.</p></article>`;
  }
  function renderCards(users){
    if(!productionReady())return;
    let section=id('collaborator-cards');if(!section){section=document.createElement('section');section.id='collaborator-cards';id('users-table').before(section);}
    section.innerHTML=`<h2>Fichas de colaboradores</h2><div class="person-cards-grid">${users.map(person=>personCard(person)).join('')}</div>`;
  }
  async function profileForm(){
    const owner=String(S.user.id);
    if(id('base-profile-card')?.dataset.owner!==owner)id('base-profile-card')?.remove();
    if(id('base-profile-form') || S.user.must_change)return;
    const response=await api('/api/profile');if(!productionReady() || String(S.user.id)!==owner || S.view!=='account' || id('base-profile-form'))return;
    const data=response.profile;
    const section=document.createElement('section');section.className='card';section.id='base-profile-card';
    section.dataset.owner=owner;
    section.innerHTML=`${personCard({...S.user,position:data.position})}<h2>${S.user.must_complete_profile?'Completa tu perfil para continuar':'Mi información'}</h2><p>Tu código de acceso es ${escapeHtml(S.user.username)}. Estos datos se guardan en la PC principal.</p><form id="base-profile-form"><div class="form-grid two">${[['full_name','Nombre completo','text'],['identity_number','Cédula','text'],['birth_date','Fecha de nacimiento','date'],['phone','Teléfono','tel'],['fleet','Flota (opcional)','text'],['position','Puesto actual','text']].map(([key,label,type])=>`<label>${label}<input name="${key}" type="${type}" value="${escapeHtml(data[key] || (key==='full_name'?S.user.name:''))}"${key==='fleet'?'':' required'} maxlength="150"></label>`).join('')}</div><div id="base-profile-error" class="notice error hidden" role="alert"></div><button type="submit" class="btn primary">Guardar mi perfil</button></form>`;
    id('view-account').prepend(section);
    id('base-profile-form').autocomplete='off';
    id('base-profile-form').onsubmit=event=>{event.preventDefault();busy(event.submitter,async()=>{await api('/api/profile',Object.fromEntries(new FormData(event.target)));section.remove();await enterApp(await api('/api/me'));toast('Perfil guardado.');},id('base-profile-error'));};
  }
  async function loadStatus(){
    statusData=await api('/api/base/status');const data=statusData.backup;
    const date=value=>new Intl.DateTimeFormat('es-DO',{timeZone:'America/Santo_Domingo',dateStyle:'medium',timeStyle:'medium'}).format(new Date(value));
    const type={manual:'Creada por administrador',automatico:'Programada',antes_restauracion:'Antes de restaurar',sin_tipo:'Copia incorporada'};
    const download=file=>`<a class="btn secondary" href="/api/base/backup-file?name=${encodeURIComponent(file.name)}" download>Descargar${file.latest?' más reciente':''}</a>`;
    id('view-base').innerHTML=`
      <section class="card"><h2>Base local · Fase 1</h2>${note('Instalación, usuarios, auditoría y respaldos. La captura de producción de la fase 2 permanece bloqueada.')}<p>La base de trabajo sigue en el disco local de la PC principal. Las carpetas de red guardan copias de seguridad.</p></section>
      <section class="card"><h2>Guardar copias en las unidades de la operativa</h2>
        <p>Puedes utilizar una o dos carpetas de las unidades de red disponibles. No necesitas USB. Por ejemplo: <strong>I:\\LaboratorioMedidas\\Respaldos</strong> y, si lo deseas, <strong>H:\\LaboratorioMedidas\\Respaldos</strong>. Son ejemplos: utiliza las rutas donde tu usuario de Windows tenga permiso para escribir.</p>
        <p>Las rutas se interpretan desde la PC principal, donde corre el programa. También se aceptan rutas de red completas, como <span class="mono">\\\\servidor\\carpeta\\LaboratorioMedidas\\Respaldos</span>.</p>
        <form id="backup-config-form"><div class="form-grid two">
          <label>Hora diaria (Santo Domingo)<input name="daily_time" type="time" required value="${escapeHtml(data.settings.daily_time)}"></label>
          <label>Primera carpeta de respaldo<input name="target1" required placeholder="I:\\LaboratorioMedidas\\Respaldos" value="${escapeHtml(data.settings.targets[0] || '')}"></label>
          <label>Segunda carpeta (opcional)<input name="target2" placeholder="H:\\LaboratorioMedidas\\Respaldos" value="${escapeHtml(data.settings.targets[1] || '')}"></label>
        </div><div id="backup-config-error" class="notice error hidden" role="alert"></div><button class="btn primary" type="submit">Guardar y comprobar carpetas</button></form>
        <p>Se permiten carpetas del mismo servidor. El estado «Verificado» comprueba los archivos guardados; no certifica discos físicos distintos. La PC, el programa y las unidades de red deben estar disponibles a la hora programada.</p>
        <p>El respaldo contiene toda la base. Los permisos de la aplicación no protegen el archivo por sí solos: configura el acceso a la carpeta con los permisos de Windows de la operativa.</p>
        <button id="backup-now" class="btn secondary" type="button">Crear respaldo ahora</button><p>Este botón siempre crea una copia local y también copia a las carpetas que hayas configurado. Funciona aunque aún no configures ninguna.</p><div id="backup-result" role="status"></div>
      </section>
      <section class="card"><h2>Copias disponibles · más reciente primero</h2>
        <p>Para guardar el estado actual, crea un respaldo ahora y descarga la primera fila, marcada <strong>Más reciente</strong>. Cada archivo contiene una copia completa; no necesitas descargar todos. Las fechas se muestran en hora de Santo Domingo.</p>
        ${data.files.length?table(['Orden','Fecha y hora','Tipo','Tamaño','Archivo','Descargar'],data.files.map((file,index)=>[index===0?badge('Más reciente','good'):String(index+1),escapeHtml(date(file.created_at)),escapeHtml(type[file.source] || file.source),`${fmt(Math.ceil(file.bytes/1024))} KB`,`<span class="mono backup-hash">${escapeHtml(file.name)}</span>`,download(file)])):note('Aún no hay copias. Pulsa «Crear respaldo ahora».')}
        <p>Carpeta local: <span class="mono backup-hash">${escapeHtml(data.local_directory)}</span></p>
        <button class="btn secondary" id="backup-refresh" type="button">Actualizar lista y estado</button>
        <details class="screen-help"><summary>¿Qué hago con el archivo descargado y cómo lo recupero?</summary>
          <ol><li>El navegador normalmente lo guarda en Descargas. Puedes copiar ese archivo .db a una carpeta de respaldo de la operativa. Si configuraste esas carpetas arriba, el programa ya guarda allí las copias automáticamente.</li>
          <li>El archivo no se abre como un documento y no se coloca sobre la base activa. Consérvalo como copia de seguridad; el programa sigue utilizando sus datos locales.</li>
          <li>Si necesitas recuperarlo, elige una copia anterior al problema. Si está en Descargas u otra carpeta, cópiala a la carpeta local de respaldos indicada arriba, o a una carpeta de respaldo configurada.</li>
          <li>Pulsa «Actualizar lista y estado». Abajo, selecciona el archivo o pega su ruta completa y pulsa «Verificar y mostrar vista previa».</li>
          <li>Revisa las cantidades, escribe el motivo, tu contraseña de administrador y RESTAURAR. Confirma solo si esa es la copia que necesitas: reemplaza los datos actuales por los del momento del respaldo.</li>
          <li>La aplicación guarda una copia del estado previo y cierra las sesiones. Después inicia sesión otra vez. En una PC de reemplazo, usa esta misma versión, completa el acceso inicial y coloca el respaldo en su carpeta de copias para seguir estos pasos.</li></ol>
        </details>
      </section>
      <section class="card"><h2>Resultado de las copias configuradas</h2><p>Verificado significa que se comprobaron la copia local y todas las carpetas configuradas en ese momento. Con incidencias significa que la copia local se creó y algún destino falta o falló. Consulta la fecha de cada ejecución; los estados anteriores se conservan como historial.</p>
        <div id="backup-runs">${table(['Fecha','Tipo','Resultado','Carpetas de esa ejecución'],data.runs.map(run=>[escapeHtml(date(run.started_at)),escapeHtml(type[run.source] || run.source),badge(run.status==='correcto'?'Verificado':'Con incidencias',run.status==='correcto'?'good':'warn'),run.copies.length?run.copies.map(copy=>`${copy.ok?'✓ Guardada':'⚠ No guardada'}: ${escapeHtml(copy.path)}${copy.error?`<small>${escapeHtml(copy.error)}</small>`:''}`).join('<br>'):'Solo copia local; no había carpetas configuradas.']))}</div>
      </section>
      <section class="card"><h2>Restaurar un respaldo</h2><p>Restaurar reemplaza la base actual; no suma ni combina registros. Primero verifica el archivo y revisa sus cantidades.</p>
        <form id="restore-preview-form"><label>Respaldo local (más reciente primero)<select name="local"><option value="">Selecciona uno o escribe la ruta de una carpeta configurada</option>${data.files.map(file=>`<option value="${escapeHtml(file.path)}">${file.latest?'MÁS RECIENTE · ':''}${escapeHtml(date(file.created_at))} · ${escapeHtml(file.name)}</option>`).join('')}</select></label>
        <label>Ruta completa de un respaldo en una carpeta configurada<input name="external" placeholder="I:\\LaboratorioMedidas\\Respaldos\\respaldo-....db"></label><button class="btn secondary" type="submit">Verificar y mostrar vista previa</button><div id="restore-preview-error" class="notice error hidden" role="alert"></div></form><div id="restore-preview"></div>
      </section>`;
    id('backup-config-form').onsubmit=event=>{event.preventDefault();busy(event.submitter,async()=>{const form=event.target;await api('/api/base/backup-config',{daily_time:form.elements.daily_time.value,targets:[form.elements.target1.value,form.elements.target2.value].map(value=>value.trim()).filter(Boolean)});toast('Carpetas comprobadas y programación guardada. Pulsa Crear respaldo ahora para copiar también a esos destinos.');},id('backup-config-error'));};
    id('backup-now').onclick=()=>busy(id('backup-now'),async()=>{const result=await api('/api/base/backup-now',{});await loadStatus();id('backup-result').innerHTML=note(result.ok?`Respaldo verificado: copia local y ${result.copies.length} carpeta(s) configurada(s). Ya puedes descargar la primera fila marcada «Más reciente».`:`Copia local creada: ${result.primary}. Descarga la primera fila marcada «Más reciente». ${result.copies.length?'Hay destinos con incidencias: '+result.copies.filter(copy=>!copy.ok).map(copy=>copy.error).join(' '):'Todavía no configuraste carpetas de la operativa; puedes hacerlo arriba.'}`,result.ok?'success':'warning');});
    id('backup-refresh').onclick=()=>busy(id('backup-refresh'),loadStatus);
    id('restore-preview-form').onsubmit=event=>{event.preventDefault();busy(event.submitter,async()=>{const form=event.target;const result=await api('/api/base/restore-preview',{path:form.elements.external.value.trim() || form.elements.local.value});showRestore(result);},id('restore-preview-error'));};
    window.LabTables?.enhance(id('view-base'));
  }
  function showRestore(preview){
    id('restore-preview').innerHTML=`<h3>Contenido verificado</h3><p>${fmt(preview.counts.users)} cuentas · ${fmt(preview.counts.production_events)} registros · ${fmt(preview.counts.audit_entries)} entradas de auditoría.</p><p class="mono backup-hash">SHA-256: ${escapeHtml(preview.sha256)}</p><p>${escapeHtml(preview.message)}</p><form id="restore-confirm-form"><label>Motivo<input name="reason" required maxlength="1500"></label><label>Tu contraseña de administración<input name="password" type="password" autocomplete="current-password" required></label><label>Escribe RESTAURAR<input name="confirm" required pattern="RESTAURAR" autocomplete="off"></label><div id="restore-confirm-error" class="notice error hidden" role="alert"></div><button class="btn danger" type="submit">Confirmar restauración</button></form>`;
    id('restore-confirm-form').onsubmit=event=>{event.preventDefault();busy(event.submitter,async()=>{await api('/api/base/restore',{...Object.fromEntries(new FormData(event.target)),token:preview.token});location.reload();},id('restore-confirm-error'));};
  }
  function theme(){
    let chosen;try{chosen=localStorage.getItem('lab-theme');}catch(_){}
    document.documentElement.dataset.theme=chosen==='light'?'light':'dark';
    const button=document.createElement('button');button.type='button';button.className='icon-button theme-toggle';button.id='theme-toggle';
    const update=()=>{const light=document.documentElement.dataset.theme==='light';button.textContent=light?'☾':'☀';button.setAttribute('aria-label',light?'Activar modo oscuro':'Activar modo claro');button.title=light?'Modo oscuro':'Modo claro';};
    button.onclick=()=>{const value=document.documentElement.dataset.theme==='light'?'dark':'light';document.documentElement.dataset.theme=value;try{localStorage.setItem('lab-theme',value);}catch(_){}update();};update();document.querySelector('.topbar-right')?.prepend(button);
  }
  window.LabFoundation={enhance,loadStatus,editUser,resetUser,renderCards};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',theme,{once:true});else theme();
})();
