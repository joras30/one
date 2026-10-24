/* Identificación visual del perfil. Los dibujos y colores no conceden permisos. */
(() => {
  'use strict';
  if (window.LabAvatars) return;

  const PALETTES = Object.freeze([
    {id:'azul',label:'Azul'}, {id:'naranja',label:'Naranja'},
    {id:'verde',label:'Verde'}, {id:'violeta',label:'Violeta'}
  ]);
  const ROLE_LABELS = Object.freeze({
    tecnico:'Colaborador',supervisor:'Supervisor',administrador:'Administrador',visitante:'Visitante',persona:'Persona'
  });
  const DEFAULT_COLORS = Object.freeze({tecnico:'azul',supervisor:'naranja',administrador:'violeta',visitante:'verde',persona:'azul'});
  const SIZES = [24,28,32,34,36,40,48,64,80,96];
  const preferences = new Map();
  let scheduled = false;
  let editorState = null;
  let refreshing = null;

  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const roleOf = value => Object.hasOwn(ROLE_LABELS,value) ? value : 'persona';
  const colorOf = (value,role) => PALETTES.some(item=>item.id===value) ? value : DEFAULT_COLORS[roleOf(role)];
  const currentUser = () => { try { return typeof S !== 'undefined' ? S.user : null; } catch (_) { return null; } };
  const apiCall = (...args) => { if (typeof api !== 'function') return Promise.reject(new Error('La aplicación todavía se está preparando.'));return api(...args); };

  function pattern(role,style='clasico') {
    const hair=style==='cabello_largo'?'<path d="M20 28q-2 16 2 20h20q4-4 2-20z" fill="#593f35"/>':style==='cabello_corto'?'<path d="M22 28v-6q10-15 20 0v6l-7-7z" fill="#593f35"/>':'';
    const face=hair+'<path d="M24 26v7c0 6 4 10 8 10s8-4 8-10v-7" fill="#dce5ef"/><path d="M28 33h1m6 0h1" stroke="#20364e" stroke-width="2" stroke-linecap="round"/><path d="M29 38q3 2 6 0" fill="none" stroke="#5a7189" stroke-width="1.5" stroke-linecap="round"/>';
    const body='<path d="M14 61v-5c0-8 8-13 18-13s18 5 18 13v5" fill="currentColor"/><path d="M27 43l5 6 5-6" fill="#dce5ef"/><path d="M32 49v12" stroke="#14263a" stroke-opacity=".55" stroke-width="2"/>';
    const helmet='<path d="M21 25c0-9 4-14 11-14s11 5 11 14" fill="currentColor"/><path d="M19 26h26M32 12v10" fill="none" stroke="#c5d4e5" stroke-width="2.5" stroke-linecap="round"/>';
    if (role==='tecnico') return face+body+helmet+'<path d="M43 40a6 6 0 0 0 6 7l-7 8a2 2 0 1 0 3 3l7-8a6 6 0 0 0 4-9l-4 4-4-1-1-4z" fill="#edf3fa" stroke="#20364e" stroke-width="1.5" stroke-linejoin="round"/><path d="M18 53h7v7h-7z" fill="#14263a" fill-opacity=".4"/>';
    if (role==='supervisor') return face+body+helmet+'<rect x="39" y="41" width="18" height="21" rx="2" fill="#edf3fa" stroke="#20364e" stroke-width="1.5"/><path d="M43 47h10M43 51h10M43 55h6M46 44v14" stroke="#617a94" stroke-width="1.3"/>';
    if (role==='administrador') return face+body+'<path d="M22 26v-4c0-8 4-12 10-12s10 4 10 12v4l-5-7-15 7z" fill="currentColor"/><path d="M46 40l10 4v8c0 5-6 10-10 12-4-2-10-7-10-12v-8z" fill="#edf3fa" stroke="#20364e" stroke-width="1.5"/><path d="M41 51l4 4 7-8" fill="none" stroke="#386a61" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>';
    if (role==='visitante') return face+body+'<path d="M22 26v-4c0-8 4-12 10-12s10 4 10 12v4l-5-7-15 7z" fill="currentColor"/><rect x="37" y="42" width="23" height="17" rx="4" fill="#edf3fa" stroke="#20364e" stroke-width="1.5"/><path d="M40 50q8-9 16 0-8 9-16 0z" fill="none" stroke="#45647f" stroke-width="1.6"/><circle cx="48" cy="50" r="2.5" fill="#45647f"/>';
    return face+body+'<path d="M22 26v-4c0-8 4-12 10-12s10 4 10 12v4l-5-7-15 7z" fill="currentColor"/>';
  }

  function render({name='',role='persona',color,style='clasico',size=36,decorative=false}={}) {
    role=roleOf(role);color=colorOf(color,role);
    size=SIZES.includes(Number(size))?Number(size):36;
    const label=`${name ? 'Avatar de '+name+' · ' : 'Avatar · '}${ROLE_LABELS[role]}`;
    return `<span class="lab-avatar lab-avatar--${color} lab-avatar--size-${size}" data-avatar-role="${role}" data-avatar-color="${color}"${decorative?' aria-hidden="true"':` role="img" aria-label="${esc(label)}"`} title="${esc(ROLE_LABELS[role])}"><svg viewBox="0 0 64 64" width="64" height="64" fill="none" aria-hidden="true" focusable="false"><circle cx="32" cy="32" r="31" class="lab-avatar-bg"/><g>${pattern(role,style)}</g></svg></span>`;
  }

  function personFor(host) {
    const me=currentUser();
    if (host.id==='account-avatar' && me) return me;
    const id=host.dataset.avatarUserId;
    if(me && String(me.id)===id)return me;
    const username=host.dataset.avatarUsername;
    try {
      if (typeof S !== 'undefined') {
        const person=(S.users || []).find(item => id ? String(item.id)===id : username && item.username===username);
        if (person) return person;
      }
    } catch (_) { /* El módulo puede cargarse antes de inicializar la aplicación. */ }
    return {id,name:host.dataset.avatarName || '',role:host.dataset.avatarRole || 'persona',avatar_color:host.dataset.avatarColor};
  }

  function paintHost(host) {
    const person=personFor(host);
    const role=roleOf(person.role);
    const color=colorOf(preferences.get(String(person.id)) || person.avatar_color,role);
    const size=Number(host.dataset.avatarSize) || (host.id==='account-avatar'?34:36);
    const signature=[person.name,role,color,person.avatar_style,size].join('|');
    if(host.dataset.avatarSignature===signature && host.querySelector(':scope > .lab-avatar'))return;
    host.dataset.avatarSignature=signature;
    host.classList.add('lab-avatar-host');
    host.innerHTML=render({name:person.name,role,color,style:person.avatar_style,size});
  }

  function setStatus(section,message,kind='') {
    const status=section.querySelector('.lab-avatar-status');
    status.textContent=message;
    status.className='lab-avatar-status'+(kind?' is-'+kind:'');
  }

  function preview(section) {
    const me=currentUser();if(!me || !editorState)return;
    const selected=section.querySelector('input[name="profile-avatar-color"]:checked')?.value || colorOf(me.avatar_color,me.role);
    editorState.selected=selected;editorState.style=section.querySelector('[name=profile-avatar-style]')?.value || 'clasico';
    section.querySelector('.lab-avatar-preview-image').innerHTML=render({name:me.name,role:me.role,color:selected,style:editorState.style,size:80});
    section.querySelector('.lab-avatar-preview-role').textContent=ROLE_LABELS[roleOf(me.role)];
    section.querySelectorAll('.lab-avatar-palette-option').forEach(label=>label.classList.toggle('is-selected',label.querySelector('input').checked));
    section.querySelector('.lab-avatar-save').disabled=editorState.saving || selected===editorState.saved && editorState.style===editorState.savedStyle;
  }

  function syncColor(person,color) {
    const role=roleOf(person.role);color=colorOf(color,role);
    person.avatar_color=color;preferences.set(String(person.id),color);
    try {
      if(typeof S!=='undefined'){
        const other=(S.users || []).find(user=>String(user.id)===String(person.id));if(other){other.avatar_color=color;other.avatar_style=person.avatar_style;}
      }
    } catch (_) { /* Las preferencias solo afectan al dibujo. */ }
    document.dispatchEvent(new CustomEvent('lab:avatar-updated',{detail:{user_id:person.id,role,color}}));
    document.querySelectorAll('#account-avatar,[data-avatar-host],.person-avatar[data-avatar-role],.avatar[data-avatar-role]').forEach(paintHost);
  }

  function ensureEditor() {
    const me=currentUser();
    const account=document.getElementById('view-account');
    const profile=document.getElementById('profile-details');
    if(!me || !account || account.classList.contains('hidden') || !profile)return;
    let section=document.getElementById('profile-avatar-editor');
    if(me.must_change){section?.classList.add('hidden');return;}
    section?.classList.remove('hidden');
    if(!section){
      editorState=null;
      section=document.createElement('section');section.id='profile-avatar-editor';section.className='card lab-avatar-editor';
      section.innerHTML='<div class="card-heading"><div><h2>Mi avatar</h2><p>Identificación visual del perfil.</p></div></div><div class="lab-avatar-preview"><span class="lab-avatar-preview-image"></span><div><strong class="lab-avatar-preview-role"></strong><p>El dibujo acompaña tu nombre y perfil. Elegir otro color conserva tus permisos.</p></div></div><form class="lab-avatar-form"><label>Dibujo del avatar<select name="profile-avatar-style"><option value="clasico">Clásico</option><option value="cabello_corto">Cabello corto</option><option value="cabello_largo">Cabello largo</option></select></label><fieldset><legend>Elige el color de tu avatar</legend><div class="lab-avatar-palette">'+PALETTES.map(item=>`<label class="lab-avatar-palette-option"><input type="radio" name="profile-avatar-color" value="${item.id}"><span class="lab-avatar-color-dot lab-avatar--${item.id}" aria-hidden="true"></span><span>${item.label}</span></label>`).join('')+'</div></fieldset><div class="lab-avatar-actions"><button type="submit" class="btn primary lab-avatar-save">Guardar avatar</button><button type="button" class="text-button lab-avatar-default">Usar color del perfil</button></div><p class="lab-avatar-status" role="status" aria-live="polite"></p><p class="lab-avatar-persistence">El dibujo y el color se guardan con tu cuenta y se incluye en los respaldos de la aplicación.</p></form>';
      const card=profile.closest('.card');(card || profile).after(section);
      section.addEventListener('change',event=>{if(event.target.matches('input[name="profile-avatar-color"],select[name="profile-avatar-style"]')){editorState.revision++;preview(section);setStatus(section,'Pulsa Guardar avatar para aplicar tu elección.');}});
      section.querySelector('.lab-avatar-default').onclick=()=>{
        const person=currentUser();if(!person)return;
        const radio=section.querySelector(`input[value="${DEFAULT_COLORS[roleOf(person.role)]}"]`);radio.checked=true;preview(section);setStatus(section,'Color del perfil seleccionado. Pulsa Guardar avatar para aplicarlo.');
      };
      section.querySelector('form').onsubmit=async event=>{
        event.preventDefault();const person=currentUser();if(!person || !editorState || editorState.saving)return;
        const expectedUser=String(person.id),color=editorState.selected;
        editorState.saving=true;editorState.revision++;preview(section);setStatus(section,'Guardando el color…');
        try{
          const result=await apiCall('/api/avatar',{color,style:editorState.style});
          if(String(currentUser()?.id)!==expectedUser)return;
          editorState.savedStyle=result.style;person.avatar_style=result.style;editorState.saved=colorOf(result.color,result.role || person.role);syncColor(person,editorState.saved);
          setStatus(section,'Avatar guardado. Tu dibujo y color ya están actualizados.','success');
        }catch(error){if(String(currentUser()?.id)===expectedUser)setStatus(section,error.message || 'No se pudo guardar el color. Intenta de nuevo.','error');}
        finally{if(String(currentUser()?.id)===expectedUser && editorState){editorState.saving=false;preview(section);}}
      };
    }
    if(!editorState || editorState.userId!==String(me.id) || editorState.role!==roleOf(me.role)){
      const color=colorOf(me.avatar_color,me.role);editorState={userId:String(me.id),role:roleOf(me.role),saved:color,selected:color,style:me.avatar_style || 'clasico',savedStyle:me.avatar_style || 'clasico',saving:false,revision:0};
      section.querySelector('[name=profile-avatar-style]').value=editorState.style;section.querySelector(`input[value="${color}"]`).checked=true;preview(section);setStatus(section,'Elige un dibujo y un color, y guarda tu avatar.');
      const expected=String(me.id);
      refreshing=apiCall('/api/avatar').then(result=>{
        if(String(currentUser()?.id)!==expected || editorState?.userId!==expected || editorState.revision!==0)return;
        const untouched=editorState.selected===color;
        if(untouched){me.avatar_style=result.style || 'clasico';editorState.savedStyle=me.avatar_style;section.querySelector('[name=profile-avatar-style]').value=me.avatar_style;}
        const loaded=colorOf(result.color,result.role || me.role);editorState.saved=loaded;syncColor(me,loaded);
        // Una respuesta lenta no reemplaza una elección que ya hizo la persona.
        if(!editorState.saving && untouched)section.querySelector(`input[value="${loaded}"]`).checked=true;
        preview(section);
      }).catch(error=>{if(editorState?.userId===expected)setStatus(section,error.message || 'No se pudo consultar el color guardado.','error');}).finally(()=>{refreshing=null;});
    }
  }

  function enhance(root=document) {
    const selectors='#account-avatar,[data-avatar-host],.person-avatar[data-avatar-role],.avatar[data-avatar-role]';
    if(root.matches?.(selectors))paintHost(root);
    root.querySelectorAll?.(selectors).forEach(paintHost);
    ensureEditor();
  }

  function schedule() {
    if(scheduled)return;scheduled=true;
    queueMicrotask(()=>{scheduled=false;enhance();});
  }

  window.LabAvatars=Object.freeze({render,enhance,palettes:PALETTES,defaultColor:role=>DEFAULT_COLORS[roleOf(role)],refresh:()=>{editorState=null;enhance();return refreshing;}});
  const start=()=>{enhance();new MutationObserver(schedule).observe(document.body,{subtree:true,childList:true});};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
})();
