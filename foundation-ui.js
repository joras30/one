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
  async function profileForm(){
    if(id('base-profile-form') || S.user.must_change)return;
    const response=await api('/api/profile');if(!productionReady() || S.view!=='account' || id('base-profile-form'))return;
    const data=response.profile;
    const section=document.createElement('section');section.className='card';section.id='base-profile-card';
    section.innerHTML=`<h2>${S.user.must_complete_profile?'Completa tu perfil para continuar':'Mi información'}</h2><p>Tu código de acceso es ${escapeHtml(S.user.username)}. Estos datos se guardan en la PC principal.</p><form id="base-profile-form"><div class="form-grid two">${[['full_name','Nombre completo','text'],['identity_number','Cédula','text'],['birth_date','Fecha de nacimiento','date'],['phone','Teléfono','tel'],['fleet','Flota (opcional)','text'],['position','Puesto actual','text']].map(([key,label,type])=>`<label>${label}<input name="${key}" type="${type}" value="${escapeHtml(data[key] || (key==='full_name'?S.user.name:''))}"${key==='fleet'?'':' required'} maxlength="150"></label>`).join('')}</div><div id="base-profile-error" class="notice error hidden" role="alert"></div><button type="submit" class="btn primary">Guardar mi perfil</button></form>`;
    id('view-account').prepend(section);
    id('base-profile-form').onsubmit=event=>{event.preventDefault();busy(event.submitter,async()=>{await api('/api/profile',Object.fromEntries(new FormData(event.target)));section.remove();await enterApp(await api('/api/me'));toast('Perfil guardado.');},id('base-profile-error'));};
  }
  async function loadStatus(){
    statusData=await api('/api/base/status');const data=statusData.backup;
    id('view-base').innerHTML=`<section class="card"><h2>Base local · Fase 1</h2>${note('Esta entrega prepara instalación, usuarios, auditoría y respaldos. La captura de producción de la fase 2 permanece bloqueada hasta tu validación.')}<p>La base de producción comienza vacía. La demo de pruebas utiliza otra carpeta.</p></section><section class="card"><h2>Respaldo diario en dos destinos externos</h2><p>Además de la copia en la PC principal, configura dos carpetas en unidades físicas distintas. La PC debe estar encendida y ambos destinos conectados.</p><form id="backup-config-form"><div class="form-grid two"><label>Hora diaria (Santo Domingo)<input name="daily_time" type="time" required value="${escapeHtml(data.settings.daily_time)}"></label><label>Primer destino externo<input name="target1" required placeholder="D:\\RespaldoLaboratorio" value="${escapeHtml(data.settings.targets[0] || '')}"></label><label>Segundo destino externo<input name="target2" required placeholder="\\\\servidor\\respaldo-laboratorio" value="${escapeHtml(data.settings.targets[1] || '')}"></label><label class="checkbox-label"><input name="confirmed" type="checkbox" required${data.settings.confirmed_distinct_media?' checked':''}> Confirmo que son ubicaciones físicas distintas entre sí y de la PC principal.</label></div><div id="backup-config-error" class="notice error hidden" role="alert"></div><button class="btn primary" type="submit">Guardar programación</button></form><p>Dos carpetas en la misma unidad no cuentan como dos respaldos externos.</p><button id="backup-now" class="btn secondary" type="button">Crear respaldo ahora</button><div id="backup-result" role="status"></div></section><section class="card"><h2>Últimos respaldos</h2><p>Correcto significa que se verificaron la copia local y las dos externas. Incompleto identifica los destinos que requieren atención.</p><div id="backup-runs">${table(['Fecha','Tipo','Estado','Ubicaciones externas'],data.runs.map(run=>[escapeHtml(prettyTime(run.started_at)),escapeHtml(run.source),escapeHtml(run.status),run.copies.map(copy=>`${copy.ok?'✓':'⚠'} ${escapeHtml(copy.path)}${copy.error?`<small>${escapeHtml(copy.error)}</small>`:''}`).join('<br>')]))}</div><p>Carpeta local: <span class="mono">${escapeHtml(data.local_directory)}</span></p><button class="btn secondary" id="backup-refresh" type="button">Actualizar estado</button></section><section class="card"><h2>Restaurar un respaldo</h2><p>Primero verifica el archivo y revisa sus cantidades. La restauración reemplaza la base actual, crea una copia previa y cierra las sesiones.</p><form id="restore-preview-form"><label>Respaldo local<select name="local"><option value="">Selecciona uno o escribe la ruta externa</option>${data.files.map(file=>`<option value="${escapeHtml(file.path)}">${escapeHtml(file.name)}</option>`).join('')}</select></label><label>Ruta de un respaldo externo configurado<input name="external" placeholder="Ruta completa al archivo .db"></label><button class="btn secondary" type="submit">Verificar y mostrar vista previa</button><div id="restore-preview-error" class="notice error hidden" role="alert"></div></form><div id="restore-preview"></div></section>`;
    id('backup-config-form').onsubmit=event=>{event.preventDefault();busy(event.submitter,async()=>{const form=event.target;await api('/api/base/backup-config',{daily_time:form.elements.daily_time.value,targets:[form.elements.target1.value,form.elements.target2.value],confirmed_distinct_media:form.elements.confirmed.checked});toast('Programación guardada.');},id('backup-config-error'));};
    id('backup-now').onclick=()=>busy(id('backup-now'),async()=>{const result=await api('/api/base/backup-now',{});id('backup-result').innerHTML=note(result.ok?'Copia local y dos copias externas verificadas.':`Respaldo incompleto. La copia local está guardada; revisa la configuración y los destinos externos. ${result.copies.filter(copy=>!copy.ok).map(copy=>copy.error).join(' ')}`,result.ok?'success':'warning');});
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
  window.LabFoundation={enhance,loadStatus,editUser,resetUser};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',theme,{once:true});else theme();
})();
