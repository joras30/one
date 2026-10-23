import {pbkdf2} from '@noble/hashes/pbkdf2.js';
import {sha256} from '@noble/hashes/sha2.js';
import {bytesToHex, hexToBytes, utf8ToBytes} from '@noble/hashes/utils.js';

globalThis.browserPbkdf2 = (password, salt, rounds) => bytesToHex(
  pbkdf2(sha256, utf8ToBytes(password), hexToBytes(salt), {c:rounds,dkLen:32}));

const DATABASE = 'laboratorio-medidas-demo-v1';
const buildVersion=new URL(import.meta.url).searchParams.get('v') || '';
let py, database, cookie='', revision=-1, queue=Promise.resolve();
const progress=(message)=>postMessage({type:'progress',message});
function openDatabase() {
  return new Promise((resolve,reject)=>{
    const request=indexedDB.open(DATABASE,1);
    request.onupgradeneeded=()=>request.result.createObjectStore('state');
    request.onsuccess=()=>resolve(request.result);
    request.onerror=()=>reject(new Error('No se pudo abrir el almacenamiento del navegador.'));
  });
}
function storedState() {
  return new Promise((resolve,reject)=>{
    const request=database.transaction('state','readonly').objectStore('state').get('sqlite');
    request.onsuccess=()=>resolve(request.result);
    request.onerror=()=>reject(new Error('No se pudo leer la prueba guardada.'));
  });
}
function saveState(value) {
  return new Promise((resolve,reject)=>{
    const transaction=database.transaction('state','readwrite');
    transaction.objectStore('state').put(value,'sqlite');
    transaction.oncomplete=resolve;
    transaction.onabort=transaction.onerror=()=>reject(new Error('No se pudo guardar. Revisa el espacio disponible y los permisos del navegador.'));
  });
}
function pythonCall(expression,value) {
  if(value!==undefined)py.globals.set('_browser_value',value);
  return py.runPython(expression);
}
function decodeBase64(encoded) {
  return Uint8Array.from(atob(encoded),char=>char.charCodeAt(0));
}
async function transaction(action) {
  if(!navigator.locks)throw new Error('Actualiza tu navegador para guardar esta demo de forma segura.');
  return navigator.locks.request(DATABASE,async()=>{
    const before=await storedState();
    if(before&&before.revision!==revision){
      pythonCall('replace_database(_browser_value)',before.image);
      revision=before.revision;cookie=before.cookie||'';
    }
    try {
      const result=await action();
      const next={image:pythonCall('snapshot()'),cookie,revision:(before?.revision||0)+1};
      await saveState(next);revision=next.revision;
      return result;
    } catch(error) {
      if(before){pythonCall('replace_database(_browser_value)',before.image);cookie=before.cookie||'';revision=before.revision;}
      throw error;
    }
  });
}
async function initialise(baseUrl) {
  progress('Preparando la demo gratuita. La primera carga puede tardar unos segundos…');
  database=await openDatabase();
  const {loadPyodide}=await import(new URL('runtime/pyodide.mjs',baseUrl).href);
  py=await loadPyodide({indexURL:new URL('runtime/',baseUrl).href});
  py.FS.mkdirTree('/app');py.FS.mkdirTree('/demo-data');
  const files=['app.py','production.py','documents.py','operational.py','analytics.py','foundation.py','catalogos.json','bridge.py'];
  await Promise.all(files.map(async(name)=>{
    const url=new URL('engine/'+name,baseUrl);if(buildVersion)url.searchParams.set('v',buildVersion);
    const response=await fetch(url);
    if(!response.ok)throw new Error('Falta un archivo de la demo. Actualiza la página.');
    py.FS.writeFile('/app/'+name,new Uint8Array(await response.arrayBuffer()));
  }));
  py.runPython("import sys; sys.path.insert(0, '/app'); import app; app.configure('/demo-data', port=8766, demo=True)");
  py.runPython(py.FS.readFile('/app/bridge.py',{encoding:'utf8'}));
  progress('Recuperando tu prueba guardada…');
  await transaction(()=>{pythonCall('initialise_demo()');});
}
async function handle(message) {
  if(message.type==='init'){await initialise(message.baseUrl);return {};}
  if(!py)throw new Error('La demo todavía se está preparando.');
  return transaction(()=>{
    if(message.type==='request'){
      py.globals.set('_browser_cookie',cookie);
      const result=JSON.parse(pythonCall('bridge_request(json.loads(_browser_value), _browser_cookie)',JSON.stringify(message)));
      const setCookie=result.headers['Set-Cookie'];
      if(setCookie)cookie=setCookie.split(';')[0];
      return {status:result.status,headers:result.headers,body:decodeBase64(result.body_base64)};
    }
    if(message.type==='save-backup'){
      return {body:new TextEncoder().encode(pythonCall('make_backup()')),filename:'laboratorio-demo-'+new Date().toISOString().slice(0,10)+'.json'};
    }
    if(message.type==='restore'){
      pythonCall('restore_backup(_browser_value)',new TextDecoder().decode(message.body));cookie='';return {};
    }
    throw new Error('Operación de demostración no reconocida.');
  });
}
onmessage=({data})=>{
  queue=queue.then(async()=>{
    try{postMessage({id:data.id,ok:true,...await handle(data)});}
    catch(error){postMessage({id:data.id,ok:false,error:error.message||String(error)});}
  });
};
