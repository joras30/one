/* Controles locales sobre tablas HTML: no alteran registros ni solicitan permisos nuevos. */
(() => {
  'use strict';
  if (window.LabTables) return;
  const instances = new WeakMap();
  const active = new Set();
  const saved = new Map();
  const collator = new Intl.Collator('es', {sensitivity: 'base', numeric: false});
  let nextId = 0;
  let pending = false;

  const fold = value => String(value ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  const clean = value => String(value ?? '').replace(/\s+/g, ' ').trim();
  const node = (tag, className, text) => {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  };

  function headersOf(table) {
    const grid = [];
    Array.from(table.tHead?.rows || []).forEach((row, ri) => {
      grid[ri] ||= [];
      let ci = 0;
      for (const cell of row.cells) {
        while (grid[ri][ci]) ci++;
        for (let r = ri; r < ri + cell.rowSpan; r++) {
          grid[r] ||= [];
          for (let c = ci; c < ci + cell.colSpan; c++) grid[r][c] = cell;
        }
        ci += cell.colSpan;
      }
    });
    const last = grid.at(-1) || [];
    return last.map((cell, index) => {
      const label = clean(cell.dataset.tableLabel || cell.textContent);
      const action = /^(?:accion(?:es)?|abrir|opciones|herramientas|gestionar)$/.test(fold(label)) ||
        (fold(label)==='detalle' && Array.from(table.tBodies).every(body => Array.from(body.rows).every(row => cellsOf(row)[index]?.querySelector('button'))));
      return {cell,index,label,action,sortable:!action && cell.colSpan===1 && cell.dataset.sortable!=='false'};
    });
  }

  function cellsOf(row) {
    const cells = [];
    for (const cell of row.cells) {
      for (let i = 0; i < cell.colSpan; i++) cells.push(cell);
    }
    return cells;
  }

  function textOf(cell, display=false) {
    if (!cell) return '';
    if (!display && cell.dataset.sortValue !== undefined) return clean(cell.dataset.sortValue);
    // SVG sparklines y controles no aportan un dato tabular ni deben repetirse en CSV.
    const clone = cell.cloneNode(true);
    clone.querySelectorAll('svg,script,style,[data-table-ignore],.lab-table-sort').forEach(el => el.remove());
    return clean(clone.textContent);
  }

  function dateValue(text) {
    let match = /^(\d{4})-(\d{2})-(\d{2})(?:\b|T)/.exec(text);
    if (match) return Number(match[1]) * 10000 + Number(match[2]) * 100 + Number(match[3]);
    match = /^(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})\b/.exec(text);
    if (match) return Number(match[3]) * 10000 + Number(match[2]) * 100 + Number(match[1]);
    match = /^(\d{1,2})\s+(?:de\s+)?(ene|feb|mar|abr|may|jun|jul|ago|sep|sept|oct|nov|dic)[a-z.]*\s+(?:de\s+)?(\d{4})\b/.exec(fold(text));
    if (match) {
      const month = {ene:1,feb:2,mar:3,abr:4,may:5,jun:6,jul:7,ago:8,sep:9,sept:9,oct:10,nov:11,dic:12}[match[2]];
      return Number(match[3]) * 10000 + month * 100 + Number(match[1]);
    }
    match = /^(\d{4})-S(\d{2})$/.exec(text);
    if (match) return Number(match[1])*100+Number(match[2]);
    match = /^(\d{4})-(\d{2})$/.exec(text);
    if (match) return Number(match[1])*10000+Number(match[2])*100;
    if (/^\d{4}$/.test(text)) return Number(text)*10000;
    return null;
  }

  function valueOf(cell, header) {
    const text = textOf(cell);
    if (!text || /^(?:—|–|-|sin base|sin meta exacta|no aplica)$/i.test(text)) return {type:'empty', value:''};
    const label = fold(header.label);
    const explicit = cell?.dataset.sortType || header.cell.dataset.sortType;
    const identifier = /(?:serie|\bsap\b|codigo|identificador|^id\b|numero de orden|^orden\b|^proceso\b)/.test(label);
    if (explicit === 'text' || (!explicit && identifier)) return {type:'text', value:text};
    if (explicit === 'date' || (!explicit && /(?:fecha|^desde$|^hasta$|periodo|intervalo)/.test(label))) {
      const date = dateValue(text);
      if (date !== null) return {type:'number', value:date};
    }
    if (explicit !== 'text') {
      const match = /^[+−-]?\s*\d[\d,]*(?:\.\d+)?/.exec(text);
      if (match) {
        const value = Number(match[0].replace(/,/g, '').replace(/−/g, '-').replace(/\s/g, ''));
        if (Number.isFinite(value)) return {type:'number', value};
      }
    }
    return {type:'text', value:text};
  }

  function compareRows(a, b, header, direction) {
    const av = a.sortValue;
    const bv = b.sortValue;
    if (av.type === 'empty' || bv.type === 'empty') return av.type === bv.type ? a.index-b.index : av.type === 'empty' ? 1 : -1;
    const difference = av.type === 'number' && bv.type === 'number'
      ? av.value-bv.value : collator.compare(String(av.value), String(bv.value));
    return difference ? difference * direction : a.index-b.index;
  }

  function tableKey(table, headers) {
    const owner = table.closest('[id]');
    if (!owner) return '';
    const siblings = Array.from(owner.querySelectorAll('table.data-table'));
    return `${owner.id}:${siblings.indexOf(table)}:${headers.map(h => h.label).join('|')}`;
  }

  function csvValue(value) {
    let text = String(value ?? '');
    if (/^[\s\u0000-\u001f]*[=+@-]/.test(text)) text = "'" + text;
    return '"' + text.replace(/"/g, '""') + '"';
  }

  function exportCsv(instance) {
    const columns = instance.headers.filter(header => !header.action);
    const lines = [columns.map(header => csvValue(header.label)).join(',')];
    for (const item of instance.filtered) {
      const cells = cellsOf(item.row);
      lines.push(columns.map(header => csvValue(textOf(cells[header.index]))).join(','));
    }
    const blob = new Blob(['\ufeff' + lines.join('\r\n') + '\r\n'], {type:'text/csv;charset=utf-8'});
    const url = URL.createObjectURL(blob);
    const link = node('a');
    link.href = url;
    link.download = `laboratorio-tabla-${instance.ownerId || 'datos'}-${new Date().toISOString().slice(0,10)}.csv`;
    document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1500);
  }

  function render(instance) {
    const {table, state, entries, headers} = instance;
    const terms = fold(state.query).split(/\s+/).filter(Boolean);
    const rows = entries.filter(item => terms.every(term => item.search.includes(term)));
    if (state.column !== null && headers[state.column]?.sortable) {
      const header=headers[state.column];
      rows.forEach(item => {item.sortValue=valueOf(cellsOf(item.row)[header.index],header);});
      rows.sort((a,b) => compareRows(a,b,headers[state.column],state.direction));
    }
    const size = state.size === 'all' ? Math.max(1, rows.length) : Number(state.size);
    const pages = Math.max(1, Math.ceil(rows.length / size));
    state.page = Math.min(pages, Math.max(1,state.page));
    const from = (state.page-1)*size;
    const visible = new Set(rows.slice(from,from+size).map(item => item.row));
    const matching = new Set(rows.map(item => item.row));
    // Mover los mismos nodos conserva listeners, botones de detalle y formularios.
    for (const body of table.tBodies) {
      const fragment = document.createDocumentFragment();
      rows.filter(item => item.body === body).forEach(item => fragment.append(item.row));
      entries.filter(item => item.body === body && !matching.has(item.row)).forEach(item => fragment.append(item.row));
      body.append(fragment);
    }
    for (const entry of entries) entry.row.hidden = !visible.has(entry.row);
    headers.forEach(header => {
      if (!header.sortable) return;
      const selected = state.column === header.index;
      header.cell.setAttribute('aria-sort',selected ? state.direction===1?'ascending':'descending' : 'none');
      const button = header.cell.querySelector('.lab-table-sort');
      if (button) {
        button.setAttribute('aria-label', `Ordenar por ${header.label}${selected&&state.direction===1?', de mayor a menor':', de menor a mayor'}`);
        const icon = button.querySelector('.lab-table-sort-icon');
        if (icon) icon.textContent = selected ? state.direction===1?'↑':'↓' : '↕';
      }
    });
    const first = rows.length ? from+1 : 0;
    const last = rows.length ? Math.min(from+size,rows.length) : 0;
    instance.count.textContent = `Se muestran ${first}–${last} de ${rows.length} filas${terms.length?` · ${entries.length} filas cargadas`:''}. Página ${state.page} de ${pages}.`;
    instance.previous.disabled = state.page===1;
    instance.next.disabled = state.page===pages;
    instance.export.disabled = rows.length===0;
    instance.empty.hidden = rows.length!==0;
    instance.filtered = rows;
    if (instance.key) saved.set(instance.key,{...state});
  }

  function refresh(table, force=true) {
    const instance = instances.get(table);
    if (!instance) return enhance(table);
    const rows = Array.from(table.tBodies).flatMap(body => Array.from(body.rows).map(row => ({row,body})));
    const existing = new Set(instance.entries.map(entry => entry.row));
    if (!force && rows.length===instance.entries.length && rows.every(item => existing.has(item.row))) return;
    const original = new Map(instance.entries.map(item => [item.row,item.index]));
    instance.entries = rows.map((item,index) => ({...item,index:original.get(item.row) ?? instance.entries.length+index,
      search:fold(cellsOf(item.row).map(cell => `${textOf(cell)} ${textOf(cell,true)}`).join(' '))}));
    render(instance);
  }

  function enhanceTable(table) {
    if (!table.tHead || !table.tBodies.length || table.dataset.tableTools==='off') return;
    if (instances.has(table)) return refresh(table,false);
    document.dispatchEvent(new CustomEvent('lab:table-before-enhance',{detail:{table}}));
    const headers = headersOf(table);
    if (!headers.length) return;
    const key = tableKey(table,headers);
    const previous = key && saved.get(key);
    const state = {query:'',size:'25',column:null,direction:1,page:1,...previous};
    if (!['10','25','50','all'].includes(state.size)) state.size='25';
    const anchor = table.closest('.table-wrap') || table;
    const owner = table.closest('[id]');
    const id = `lab-table-${++nextId}`;
    const tools = node('div','lab-table-tools'); tools.dataset.tableTools=id;
    const label = node('label','lab-table-search-label','Buscar en esta tabla');
    const search = node('input','lab-table-search'); search.type='search'; search.placeholder='Escribe una serie, nombre o dato…'; search.value=state.query;
    label.append(search); tools.append(label);
    const sizeLabel = node('label','lab-table-size-label','Filas por página');
    const size = node('select','lab-table-size');
    for (const [value,text] of [['10','10'],['25','25'],['50','50'],['all','Todas']]) {
      const option = node('option','',text); option.value=value; size.append(option);
    }
    size.value=state.size; sizeLabel.append(size); tools.append(sizeLabel);
    const reset = node('button','btn small secondary lab-table-reset','Restablecer tabla'); reset.type='button';
    const download = node('button','btn small secondary lab-table-export','Descargar CSV filtrado'); download.type='button';
    download.title='Descarga todas las filas que coinciden con la búsqueda, de todas las páginas de esta tabla cargada.';
    tools.append(reset,download);
    const hint = node('p','lab-table-hint','Toca un encabezado para ordenar. La búsqueda filtra las filas cargadas; los registros se conservan.');
    const serverPage = table.closest('#records-table,[data-server-page="true"]');
    if (serverPage) hint.textContent='Esta tabla muestra la página de registros cargada. Para consultar otra, usa la paginación de Registros. Busca aquí o toca un encabezado para ordenar esta página.';
    if (table.tFoot) hint.textContent+=' Los totales del pie corresponden al informe completo y no cambian al buscar.';
    tools.append(hint);
    const footer = node('div','lab-table-footer');
    const count = node('p','lab-table-count'); count.id=id+'-count'; count.setAttribute('role','status'); count.setAttribute('aria-live','polite');
    const empty = node('p','lab-table-empty','No hay coincidencias. Cambia la búsqueda o pulsa Restablecer tabla.'); empty.hidden=true;
    const pages = node('div','lab-table-pages');
    const back = node('button','btn small secondary lab-table-prev','← Anterior'); back.type='button';
    const next = node('button','btn small secondary lab-table-next','Siguiente →'); next.type='button';
    back.setAttribute('aria-label','Página anterior de esta tabla'); next.setAttribute('aria-label','Página siguiente de esta tabla');
    pages.append(back,next); footer.append(count,empty,pages);
    search.setAttribute('aria-describedby',count.id);
    anchor.before(tools); anchor.after(footer);
    const instance = {table,key,ownerId:owner?.id,headers,state,tools,footer,count,empty,previous:back,next,export:download,filtered:[],entries:[]};
    instance.entries = Array.from(table.tBodies).flatMap(body => Array.from(body.rows).map(row => ({row,body})))
      .map((item,index) => ({...item,index,search:fold(cellsOf(item.row).map(cell => `${textOf(cell)} ${textOf(cell,true)}`).join(' '))}));
    instances.set(table,instance); active.add(instance);
    headers.forEach(header => {
      if (!header.sortable) return;
      header.cell.dataset.tableLabel=header.label;
      const button = node('button','lab-table-sort'); button.type='button'; button.dataset.columnIndex=header.index;
      const icon = node('span','lab-table-sort-icon','↕'); icon.setAttribute('aria-hidden','true');
      if (header.cell.querySelector('button,a,input,select')) button.append(node('span','sr-only',`Ordenar ${header.label}`));
      else {
        const title=node('span','lab-table-sort-label');
        while (header.cell.firstChild) title.append(header.cell.firstChild);
        button.append(title);
      }
      button.append(icon); header.cell.append(button);
      button.addEventListener('click',() => {
        state.direction=state.column===header.index?-state.direction:1;
        state.column=header.index; state.page=1; render(instance);
      });
    });
    search.addEventListener('input',() => {state.query=search.value;state.page=1;render(instance);});
    size.addEventListener('change',() => {state.size=size.value;state.page=1;render(instance);});
    reset.addEventListener('click',() => {Object.assign(state,{query:'',size:'25',column:null,direction:1,page:1});search.value='';size.value='25';render(instance);});
    back.addEventListener('click',() => {state.page--;render(instance);});
    next.addEventListener('click',() => {state.page++;render(instance);});
    download.addEventListener('click',() => exportCsv(instance));
    table.dataset.tableEnhanced='true';
    render(instance);
  }

  function enhance(root=document) {
    for (const instance of active) {
      if (!instance.table.isConnected) {instance.tools.remove();instance.footer.remove();active.delete(instance);}
    }
    if (root.matches?.('table.data-table')) enhanceTable(root);
    root.querySelectorAll?.('table.data-table').forEach(enhanceTable);
  }

  function resetAll() {
    saved.clear();
    for (const instance of active) {
      Object.assign(instance.state,{query:'',size:'25',column:null,direction:1,page:1});
      instance.tools.querySelector('.lab-table-search').value='';
      instance.tools.querySelector('.lab-table-size').value='25';
      render(instance);
    }
  }

  const observer = new MutationObserver(records => {
    if (!records.some(record => Array.from(record.addedNodes).some(item => item.nodeType===1 &&
      (item.matches?.('table.data-table,tbody,tr') || item.querySelector?.('table.data-table'))))) return;
    if (!pending) {pending=true;queueMicrotask(() => {pending=false;enhance();});}
  });
  function start() {enhance();observer.observe(document.body,{childList:true,subtree:true});}
  window.LabTables = {enhance,refresh,resetAll};
  if (document.readyState==='loading') document.addEventListener('DOMContentLoaded',start,{once:true});
  else start();
})();
