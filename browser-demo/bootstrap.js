const baseUrl=new URL('./',document.baseURI).href;
const buildVersion=new URL(import.meta.url).searchParams.get('v') || '';
const versionedUrl=(name)=>{const url=new URL(name,baseUrl);if(buildVersion)url.searchParams.set('v',buildVersion);return url;};
const worker=new Worker(versionedUrl('worker.js'),{type:'module'});
const pending=new Map();let sequence=0;
const loader=document.getElementById('demo-loader');
const status=document.getElementById('demo-status');
const originalFetch=window.fetch.bind(window);
function rpc(message){return new Promise((resolve,reject)=>{
  const id=++sequence;pending.set(id,{resolve,reject});worker.postMessage({id,...message});
});}
worker.onmessage=({data})=>{
  if(data.type==='progress'){status.textContent=data.message;return;}
  const request=pending.get(data.id);if(!request)return;
  pending.delete(data.id);data.ok?request.resolve(data):request.reject(new Error(data.error));
};
worker.onerror=()=>{status.textContent='No se pudo iniciar la demo. Actualiza la página y utiliza un navegador reciente.';
  for(const request of pending.values())request.reject(new Error(status.textContent));pending.clear();};
function saveFile(body,name,type='application/octet-stream'){
  const link=document.createElement('a');link.href=URL.createObjectURL(new Blob([body],{type}));link.download=name;
  document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(link.href),2000);
}
function report(error){document.getElementById('demo-notification').textContent=error.message||String(error);}
window.fetch=async(input,options={})=>{
  const url=new URL(typeof input==='string'?input:input.url,document.baseURI);
  const apiPath=url.pathname.startsWith('/api/')?url.pathname:url.pathname.startsWith(new URL(baseUrl).pathname+'api/')?'/'+url.pathname.slice(new URL(baseUrl).pathname.length):null;
  if(url.origin===location.origin&&apiPath){
    try{
      const result=await rpc({type:'request',method:options.method||'GET',path:apiPath+url.search,headers:Object.fromEntries(new Headers(options.headers||{})),body:options.body||null});
      if(apiPath==='/api/backup'&&result.status===200){const backup=await rpc({type:'save-backup'});saveFile(backup.body,backup.filename,'application/json');}
      return new Response(result.body,{status:result.status,headers:result.headers});
    }catch(error){return new Response(JSON.stringify({error:error.message}),{status:503,headers:{'Content-Type':'application/json'}});}
  }
  return originalFetch(input,options);
};
document.addEventListener('click',async(event)=>{
  const link=event.target.closest('a[href]');if(!link)return;
  const url=new URL(link.href);
  if(url.origin!==location.origin||!url.pathname.startsWith('/api/'))return;
  event.preventDefault();
  try{
    const response=await fetch(url.href);
    if(!response.ok)throw new Error((await response.json()).error);
    const disposition=response.headers.get('Content-Disposition')||'';
    const name=disposition.match(/filename="([^"]+)"/)?.[1]||url.pathname.split('/').pop();
    saveFile(await response.arrayBuffer(),name,response.headers.get('Content-Type'));
  }catch(error){report(error);}
},true);
document.getElementById('demo-backup').onclick=async()=>{
  try{const backup=await rpc({type:'save-backup'});saveFile(backup.body,backup.filename,'application/json');}catch(error){report(error);}
};
document.getElementById('demo-restore').onchange=async(event)=>{
  const file=event.target.files[0];if(!file)return;
  if(file.size>32*1024*1024){report(new Error('El respaldo supera el tamaño admitido.'));return;}
  if(!confirm('¿Restaurar este respaldo de demostración en este navegador? Reemplazará tu prueba actual.'))return;
  try{await rpc({type:'restore',body:new Uint8Array(await file.arrayBuffer())});location.reload();}catch(error){report(error);}
  finally{event.target.value='';}
};
const banner=document.getElementById('demo-banner');
new ResizeObserver(()=>document.documentElement.style.setProperty('--demo-banner-height',banner.offsetHeight+'px')).observe(banner);
try{
  await rpc({type:'init',baseUrl});
  for(const name of ['table-tools.js','profile-avatars.js','drilldown.js','foundation-ui.js','app.js'])await new Promise((resolve,reject)=>{
    const script=document.createElement('script');script.src=versionedUrl(name);script.onload=resolve;
    script.onerror=()=>reject(new Error('No se pudo cargar la interfaz. Recarga la página para volver a intentarlo.'));
    document.body.append(script);
  });
  loader.remove();
}catch(error){status.textContent=error.message;}
