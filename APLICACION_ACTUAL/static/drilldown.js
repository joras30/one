/* Navegación de indicadores a sus registros. No modifica la base de datos. */
(() => {
  'use strict';
  const descriptors = new WeakMap();
  const rowTables = new WeakSet();
  let dialog, current = null, history = [], requestNumber = 0, observer, scheduled = false;
  const metricText = {
    events: 'Registros de actividad que coinciden con esta selección.',
    reviews: 'Cada fila es una revisión técnica. Revisar otra vez la misma serie crea otra revisión.',
    approved: 'Revisiones con el resultado Apto. El medidor fue aprobado en esa revisión.',
    rejected: 'Revisiones con el resultado No apto. Consulta el registro para conocer el fallo informado.',
    evaluated: 'Evaluadas significa Apto más No apto. La tasa de aprobación divide las aptas entre esas evaluadas; los pendientes quedan fuera.',
    pending: 'Revisiones cuyo resultado registrado es Pendiente.',
    without_result: 'Revisiones en las que todavía no se informó un resultado.',
    unfinished: 'Revisiones pendientes y revisiones sin resultado. Se muestran separadas de las evaluadas.',
    identified: 'Una fila por serie identificada en esta selección. Si tiene varios registros, se muestra el más reciente; esto no cuenta equipos de lotes sin serie.',
    reentries: 'Revisiones adicionales de una serie dentro del período. Se excluye la primera revisión de cada serie y las revisiones sin serie.',
    calibrations: 'Revisiones con una referencia y una medición válidas. Consulta los valores y la tolerancia en cada registro.',
    outside_tolerance: 'Calibraciones cuya desviación, en valor absoluto, supera la tolerancia registrada.'
  };
  const byId = (id) => document.getElementById(id);
  const ready = () => { try { return typeof S !== 'undefined' && Boolean(S.user); } catch (_) { return false; } };
  const params = (value) => new URLSearchParams(value || '');
  const esc = (value) => escapeHtml(value);
  function withQuery(base, changes) {
    const query = params(base);
    for (const [key, value] of Object.entries(changes || {})) {
      if (value === null || value === undefined || value === '') query.delete(key);
      else query.set(key, String(value));
    }
    query.delete('page'); query.delete('page_size');
    return query.toString();
  }
  function baseQuery(source) {
    return source === 'quality' ? S.qualityQuery || '' : source === 'comparison' ? S.comparisonQuery || '' : S.dashboardQuery || '';
  }
  function comparisonBase(row, letter = 'b') {
    const query = params(baseQuery('comparison')), period = S.comparison?.[`period_${letter}`];
    for (const name of [...query.keys()]) if (name.startsWith('a_') || name.startsWith('b_') || name === 'group_by') query.delete(name);
    return withQuery(query, {desde: period?.from, hasta: period?.to, responsible_id: row.responsible_id || query.get('responsible_id'),
      activity_id: row.activity_id || query.get('activity_id'), unit: row.unit});
  }
  function description(title, query, metric = 'events', explanation = '', extra = {}) {
    return {mode:'records', title, query:withQuery(query, {metric, state:'valido'}), metric,
      explanation: explanation || metricText[metric] || metricText.events, ...extra};
  }
  function bind(node, desc, hint = true) {
    if (!node || !desc || descriptors.has(node)) return;
    descriptors.set(node, desc);
    node.classList.add('detail-trigger');
    node.dataset.detailMetric = desc.metric || desc.mode || 'events';
    node.dataset.detailQuery = desc.query || '';
    if (!node.matches('button,a,input,select,textarea')) {
      node.setAttribute('role', 'button'); node.setAttribute('tabindex', '0');
    }
    node.setAttribute('aria-label', `${desc.title}. Abrir datos de esta selección.`);
    if (hint && node.matches('.metric-card,.scope-stat,.unit-chip')) {
      const text = document.createElement('span'); text.className = 'detail-open-hint'; text.dataset.tableIgnore=''; text.textContent = 'Ver datos →'; node.append(text);
    }
  }
  function bindRow(row, desc) { bind(row, desc, false); }
  function bindCell(cell, desc) {
    if (!cell || descriptors.has(cell)) return;
    bind(cell, desc, false); cell.classList.add('detail-cell');
    const hint = document.createElement('span'); hint.className = 'detail-cell-hint'; hint.dataset.tableIgnore=''; hint.textContent = 'Ver →'; cell.append(hint);
  }
  function annotateTable(tableNode) {
    if (!ready() || rowTables.has(tableNode) || tableNode.closest('#detail-dialog')) return;
    rowTables.add(tableNode);
    const rows = [...(tableNode.tBodies[0]?.rows || [])];
    const wrap = tableNode.closest('[id]')?.id;
    if (wrap === 'quality-technicians') {
      const entries = S.quality?.by_technician || [];
      rows.forEach((row, index) => {
        const item = entries[index]; if (!item) return;
        const query = withQuery(baseQuery('quality'), {activity_id:'revision', responsible_id:item.responsible_id});
        bindRow(row, description(`Revisiones de ${item.name}`, query, 'reviews'));
        for (const [column, metric] of [[5,'approved'],[6,'rejected'],[7,'outside_tolerance'],[8,'calibrations']])
          bindCell(row.cells[column], description(`${item.name}: ${metric === 'approved' ? 'aprobadas' : metric === 'rejected' ? 'rechazadas' : metric === 'calibrations' ? 'mediciones de calibración' : 'fuera de tolerancia'}`, query, metric));
      });
    } else if (wrap === 'quality-failures-table') {
      rows.forEach((row, index) => {
        const item = S.quality?.detailed_failures?.[index];
        if (item) bindRow(row, {mode:'record', recordId:item.event_id, title:`Registro del medidor ${item.serial || 'sin serie'}`});
      });
    } else if (wrap === 'comparison-table') {
      const entries = S.comparison?.rows || [];
      rows.forEach((row, index) => {
        const item = entries[index]; if (!item) return;
        const label = [item.responsible_name, item.activity_name].filter(Boolean).join(' · ');
        const identityColumns = S.comparison?.group_by === 'activity' ? 2 : 3;
        const a = description(`Período A · ${label}`, comparisonBase(item, 'a'), 'events', `Producción del período A, usado como referencia. Las cantidades conservan la unidad ${item.unit}.`);
        const b = description(`Período B · ${label}`, comparisonBase(item, 'b'), 'events', `Producción del período B. La variación se obtiene restando A a B; una cantidad no representa necesariamente equipos físicos únicos.`);
        bindRow(row, b); bindCell(row.cells[identityColumns], a); bindCell(row.cells[identityColumns + 1], b);
      });
    } else if (wrap === 'quality-timeline') {
      rows.forEach((row, index) => {
        const item = S.quality?.by_period?.[index]; if (!item) return;
        const query = withQuery(baseQuery('quality'), {desde:item.from, hasta:item.to, activity_id:'revision'});
        bindRow(row, description(`Revisiones · ${item.label}`, query, 'reviews'));
        for (const [column, metric] of [[2,'approved'],[3,'rejected'],[4,'pending'],[5,'without_result'],[6,'evaluated'],[7,'outside_tolerance']])
          bindCell(row.cells[column], description(`Calidad · ${item.label}`, query, metric));
      });
    } else if (wrap === 'dashboard-trend-table') {
      const series = S.dashboard?.trend?.series?.find((item) => item.id === byId('dashboard-series')?.value);
      rows.forEach((row, index) => {
        const point = series?.points?.[index]; if (!point) return;
        bindRow(row, description(`${series.activity_name} · ${point.label}`, withQuery(baseQuery('dashboard'), {
          activity_id:series.activity_id, unit:series.unit, desde:point.from, hasta:point.to}), 'events'));
      });
    } else if (wrap === 'comparison-series-a' || wrap === 'comparison-series-b') {
      const letter = wrap.endsWith('-a') ? 'a' : 'b';
      rows.forEach((row, index) => {
        const bucket = S.comparison?.[`series_${letter}`]?.[index]; if (!bucket) return;
        bindRow(row, description(`Período ${letter.toUpperCase()} · ${bucket.label}`,
          withQuery(comparisonBase({}, letter), {desde:bucket.from, hasta:bucket.to}), 'events'));
      });
    } else if (wrap === 'dashboard-goals' || wrap === 'goals-table') {
      const goals = wrap === 'dashboard-goals' ? (S.dashboard?.goals || []).slice(0, 5) : S.goals || [];
      rows.forEach((row, index) => {
        const goal = goals[index]; if (!goal) return;
        bindRow(row, description(`Producción de la meta · ${goal.responsible_name}`, withQuery('', {
          desde:goal.start_date, hasta:goal.end_date, responsible_id:goal.responsible_id, activity_id:goal.activity_id, unit:goal.unit}),
        'events', `Esta meta pide ${fmt(goal.target)} ${goal.unit}. Aquí se muestra su producción en todo el período de la meta, sin aplicar los filtros del resumen.`));
      });
    } else if (wrap === 'records-table') {
      rows.forEach((row, index) => {
        const record = S.records?.[index]; if (record) bindRow(row, {mode:'record', recordId:record.id, title:'Detalle del registro'});
      });
    }
  }
  function annotateCards() {
    const dashboardQuery = baseQuery('dashboard');
    const hero = {reviews:['Revisiones realizadas','reviews'], approved:['Revisiones aprobadas','approved'],
      rejected:['Revisiones rechazadas','rejected'], 'approval-rate':['Revisiones evaluadas y tasa de aprobación','evaluated']};
    for (const card of document.querySelectorAll('#metrics-grid [data-metric]')) {
      const value = hero[card.dataset.metric]; if (value) bind(card, description(value[0], dashboardQuery, value[1]));
    }
    const secondary = [
      description('Registros de actividad',dashboardQuery), description('Series identificadas',dashboardQuery,'identified'),
      description('Reingresos de revisión',dashboardQuery,'reentries'),
      {mode:'orders',title:'Lotes pendientes',orders:(S.dashboard?.batch_progress || []).filter((order) => order.pending === null || order.pending > 0),
        explanation:'Órdenes con unidades pendientes o cantidad esperada por confirmar. El saldo acumula entregas hasta la fecha de corte.',
        cutoff:params(dashboardQuery).get('hasta') || today(),aggregateCount:S.dashboard?.receipts_pending,visitor:isVisitor()},
      description('Revisiones sin concluir',dashboardQuery,'unfinished')
    ];
    document.querySelectorAll('#dashboard-scope .scope-stat').forEach((card, index) => bind(card, secondary[index]));
    document.querySelectorAll('#unit-summary .unit-chip').forEach((card, index) => {
      const unit = Object.keys(S.dashboard?.totals_by_unit || {})[index];
      if (unit) bind(card, description(`Producción en ${unit}`,withQuery(dashboardQuery,{unit}), 'events',
        `Se muestran los registros cuya cantidad se expresa en ${unit}. La suma de cantidades es distinta del número de filas.`));
    });
    const qualityMetrics = [
      ['Revisiones técnicas','reviews'],['Tasa de aprobación','evaluated'],['Tasa de rechazo','evaluated'],['Revisiones sin concluir','unfinished'],
      ['Mediciones de calibración','calibrations'],['Fuera de tolerancia','outside_tolerance'],['Desviación media','calibrations'],['Desviación absoluta media','calibrations']
    ];
    document.querySelectorAll('#quality-metrics .metric-card').forEach((card, index) => {
      const value = qualityMetrics[index]; if (value) bind(card, description(value[0],withQuery(baseQuery('quality'),{activity_id:'revision'}),value[1]));
    });
    document.querySelectorAll('#comparison-metrics .metric-card').forEach((card, index) => {
      const letter = index === 0 ? 'a' : 'b';
      bind(card, description(`Registros del período ${letter.toUpperCase()}`,comparisonBase({},letter),'events',index > 1
        ? 'La variación compara ambos períodos. Aquí se abre el período B; puedes abrir A desde su cuadro o desde la columna Cantidad A.' : metricText.events));
    });
    const orders = S.orders || [];
    const orderKinds = [orders.filter((o) => o.expected !== null), orders, orders.filter((o) => o.pending !== null && o.pending > 0), orders.filter((o) => o.expected > 0),
      orders.filter((o) => o.signal==='rojo' && o.state!=='cerrada'),orders.filter((o) => o.expected === null)];
    document.querySelectorAll('#receipts-metrics .metric-card').forEach((card,index) => {
      bind(card, {mode:'orders',title:card.querySelector('.metric-label')?.textContent || 'Órdenes de recepción',orders:orderKinds[index] || orders,
        cutoff:today(),explanation:'Cada fila identifica una orden. Recibido suma sus entregas válidas; pendiente compara lo recibido con la cantidad esperada. Abre una orden para ver sus entregas.'});
    });
    document.querySelectorAll('#dashboard-lots .lot-row').forEach((row,index) => {
      const order = S.dashboard?.batch_progress?.[index]; if (order) bindRow(row,{mode:'order',orderId:order.id,orderSnapshot:order,
        cutoff:params(dashboardQuery).get('hasta') || today(),title:`Proceso ${order.process}`});
    });
  }
  function annotateChart(node) {
    if (descriptors.has(node)) return;
    const chartId = node.closest('.chart-container')?.id, label = node.dataset.series;
    const query = baseQuery('dashboard'); let desc;
    if (chartId === 'chart-day') {
      const series = S.dashboard?.trend?.series?.find((item) => item.id === byId('dashboard-series')?.value);
      const point = series?.points?.find((item) => (item.from || item.date) === node.dataset.date);
      if (series && point) desc=description(`${series.activity_name} · ${point.label}`,withQuery(query,{
        activity_id:series.activity_id,unit:series.unit,desde:point.from,hasta:point.to}), 'events');
    } else if (chartId === 'chart-activity') {
      const unit = node.dataset.unit;
      const entries = (S.charts.activity?.data || []).filter((item) => item.label === label && (!unit || item.unit === unit));
      if (entries.length === 1) desc=description(`${label} · ${entries[0].unit}`,withQuery(query,{activity_name:label,unit:entries[0].unit}), 'events');
    } else if (chartId === 'chart-voltage') {
      desc=description(`Registros · ${label}`,withQuery(query,label === 'Sin voltaje' ? {voltage:null,voltage_missing:1} : {voltage:label,voltage_missing:null}));
    } else if (chartId === 'chart-collaborator') {
      const person = (S.dashboard?.by_collaborator || []).find((item) => item.label === label);
      if (person?.responsible_id) desc=description(`Actividad de ${label}`,withQuery(query,{responsible_id:person.responsible_id}));
    } else if (chartId === 'chart-batch-progress') {
      const order = (S.dashboard?.batch_progress || []).find((item) => item.process === label);
      if (order) desc={mode:'order',orderId:order.id,orderSnapshot:order,cutoff:params(query).get('hasta') || today(),title:`Proceso ${order.process}`};
    } else if (chartId === 'chart-quality-results') {
      const metrics = {Aprobación:'evaluated',Aprobadas:'approved',Rechazadas:'rejected',Pendientes:'pending','Sin resultado':'without_result'};
      if (metrics[label]) desc=description(label,withQuery(baseQuery('quality'),{activity_id:'revision'}),metrics[label]);
    } else if (chartId === 'chart-quality-failures') {
      desc=description(`Fallo: ${label}`,withQuery(baseQuery('quality'),{activity_id:'revision',failure:isVisitor()?null:label}), 'reviews',
        isVisitor() ? 'Tu perfil muestra resultados agrupados. Los textos de fallos y los registros individuales requieren un perfil autorizado.' : 'Revisiones que contienen este fallo informado; un fallo no atribuye automáticamente un error al técnico.');
    } else if (chartId === 'chart-comparison') {
      const letter = label === 'A' ? 'a' : 'b';
      const row = {responsible_id:node.dataset.responsibleId || null,activity_id:node.dataset.activityId || null,unit:node.dataset.unit};
      if (node.hasAttribute('data-unit')) desc=description(`Período ${letter.toUpperCase()} · ${node.dataset.category || 'Producción'}`,comparisonBase(row,letter));
    }
    if (desc) bind(node,desc,false);
  }
  function scopeText(query) {
    const q = params(query), parts = [];
    if (q.get('desde') || q.get('hasta')) parts.push(`Fecha de trabajo: ${q.get('desde') ? prettyDate(q.get('desde')) : 'inicio del historial'} al ${q.get('hasta') ? prettyDate(q.get('hasta')) : 'último registro'}`);
    for (const [key,label] of [['activity_name','Actividad'],['unit','Unidad'],['sap','SAP'],['voltage','Voltaje'],['brand','Marca'],['model','Modelo'],['condition','Condición'],['failure','Fallo']]) if (q.get(key)) parts.push(`${label}: ${q.get(key)}`);
    if (q.get('voltage_missing')) parts.push('Sin voltaje informado');
    if (q.get('activity_id')) parts.push(`Actividad: ${S.activities?.find((a) => a.id === q.get('activity_id'))?.name || q.get('activity_id')}`);
    if (q.get('responsible_id')) parts.push(`Colaborador: ${S.users?.find((p) => String(p.id) === q.get('responsible_id'))?.name || 'Responsable de esta selección'}`);
    return parts.join(' · ') || 'Todo el alcance permitido para tu cuenta';
  }
  function ensureDialog() {
    if (dialog) return dialog;
    dialog=document.createElement('dialog');dialog.id='detail-dialog';dialog.className='detail-dialog';dialog.setAttribute('aria-labelledby','detail-title');
    dialog.innerHTML='<header class="detail-dialog-heading"><button id="detail-back" type="button" class="btn small secondary hidden">← Volver a la lista</button><h2 id="detail-title"></h2><button id="detail-close" type="button" class="icon-button" aria-label="Cerrar detalle y volver al tablero">✕</button></header><div id="detail-content" class="detail-dialog-content"></div>';
    document.body.append(dialog);
    byId('detail-close').onclick=close;
    byId('detail-back').onclick=() => {const previous=history.pop();if(previous){current=previous;render();}};
    dialog.addEventListener('click',(event) => {if(event.target===dialog){const r=dialog.getBoundingClientRect();if(event.clientX<r.left || event.clientX>r.right || event.clientY<r.top || event.clientY>r.bottom)close();}});
    dialog.addEventListener('close',() => {
      // El evento close se entrega en otra tarea: una apertura posterior ya
      // puede estar activa. Un cierre viejo no debe borrar ese nuevo detalle.
      if(dialog.open)return;
      requestNumber++;current=null;history=[];byId('detail-content').replaceChildren();
    });
    return dialog;
  }
  function close() { if(dialog?.open)dialog.close(); }
  async function open(desc) {
    ensureDialog();history=[];current={...desc,page:1,pageSize:25,search:''};
    if(!dialog.open)dialog.showModal();await render();
  }
  function top() {
    byId('detail-title').textContent=current.title;
    byId('detail-back').classList.toggle('hidden',!history.length);
  }
  function loading() { byId('detail-content').innerHTML='<p class="detail-loading" role="status">Buscando los datos de esta selección…</p>'; }
  function fail(error) {
    const content=byId('detail-content');content.replaceChildren();const note=document.createElement('p');note.className='notice error';note.setAttribute('role','alert');note.textContent=error.message || 'No se pudo abrir el detalle.';content.append(note);
    const retry=document.createElement('button');retry.type='button';retry.className='btn secondary';retry.textContent='Intentar de nuevo';retry.onclick=render;content.append(retry);
  }
  function intro() { return `<section class="detail-explanation"><h3>Qué estás viendo</h3><p>${esc(current.explanation || metricText.events)}</p><p id="detail-query-summary" class="detail-query-summary">${esc(scopeText(current.query))}</p></section>`; }
  function recordTable(records) {
    return table(['Fecha de trabajo','Actividad','Serie / SAP','Cantidad y unidad','Responsable','Resultado','Abrir'],records.map((record) => [
      esc(prettyDate(record.work_date)),esc(record.activity_name),recordSummary(record),`${fmt(record.quantity)} ${esc(record.unit)}`,
      esc(record.responsible_name),esc(record.data?.resultado || 'Sin resultado informado'),`<button type="button" class="btn small secondary" data-detail-record="${record.id}">Ver registro →</button>`]),'No hay registros que coincidan con esta selección.');
  }
  async function renderRecords(ticket) {
    const query=params(current.query);query.set('page',String(current.page));query.set('page_size',String(current.pageSize));
    if(current.search)query.set('search',current.search);
    const result=await api(`/api/detalle?${query}`);if(ticket!==requestNumber || !dialog.open)return;
    current.page=result.page || 1;current.result=result;
    if(result.detail_allowed===false){renderAggregate(result);return;}
    const quantity=Object.entries(result.summary?.totals_by_unit || {}).map(([unit,value]) => `${fmt(value)} ${esc(unit)}`).join(' · ');
    const exportQuery=params(query);exportQuery.delete('page');exportQuery.delete('page_size');
    byId('detail-content').innerHTML=`${intro()}<div class="detail-result-heading"><p id="detail-total"><strong>${fmt(result.total)}</strong> ${current.metric==='identified'?'series identificadas':'registros'} en esta selección${quantity?`<small>Cantidad de producción: ${quantity}</small>`:''}</p><div class="export-actions">${['csv','xlsx','pdf'].map((format) => `<a class="btn small secondary" href="/api/export.${format}?${esc(exportQuery)}">${format==='xlsx'?'Excel':format.toUpperCase()} · selección completa</a>`).join('')}</div></div><form id="detail-search-form" class="detail-search-form"><label>Buscar en todos estos registros<input id="detail-search" type="search" maxlength="200" placeholder="Serie, SAP, marca, nombre o fecha" value="${esc(current.search)}"></label><button type="submit" class="btn secondary">Buscar</button><button id="detail-clear-search" type="button" class="text-button">Limpiar búsqueda</button></form><p class="detail-table-tip">Toca «Ver registro» para abrir su información completa. Los encabezados permiten ordenar; la búsqueda de arriba revisa toda la selección.</p><div id="detail-records" data-table-scope="page">${recordTable(result.records || [])}</div><div class="detail-pagination"><label>Registros por página<select id="detail-page-size">${[25,50,100,200].map((size) => `<option value="${size}"${size===current.pageSize?' selected':''}>${size}</option>`).join('')}</select></label><span id="detail-page-label" role="status">Página ${fmt(current.page)} de ${fmt(result.pages || 1)}</span><div><button id="detail-prev" type="button" class="btn small secondary"${current.page<=1?' disabled':''}>← Anterior</button><button id="detail-next" type="button" class="btn small secondary"${current.page>=(result.pages || 1)?' disabled':''}>Siguiente →</button></div></div>`;
    byId('detail-search-form').onsubmit=(event) => {event.preventDefault();current.search=byId('detail-search').value.trim();current.page=1;render();};
    byId('detail-clear-search').onclick=() => {current.search='';current.page=1;render();};
    byId('detail-page-size').onchange=() => {current.pageSize=Number(byId('detail-page-size').value);current.page=1;render();};
    byId('detail-prev').onclick=() => {current.page--;render();};byId('detail-next').onclick=() => {current.page++;render();};
    byId('detail-records').dataset.serverPage='true';
    const tableNode=byId('detail-records').querySelector('table');if(tableNode){tableNode.dataset.tableScope='page';tableNode.dataset.serverPage='true';}
    window.LabTables?.enhance(byId('detail-content'));
  }
  function renderAggregate(result) {
    const byActivity=result.breakdown?.by_activity || [],byDay=result.breakdown?.by_day || [];
    byId('detail-content').innerHTML=`${intro()}<p id="detail-total"><strong>${fmt(result.total)}</strong> ${current.metric==='identified'?'series identificadas':'registros'} en esta selección.</p><div class="notice soft">Tu perfil visitante permite explorar totales. Las series y los datos de personas se consultan con un perfil autorizado.</div><section id="detail-aggregate"><h3>Cantidad de producción por actividad</h3>${table(['Actividad','Cantidad','Unidad'],byActivity.map((item) => [esc(item.activity_name || item.label || item.name || ''),fmt(item.quantity ?? item.value),esc(item.unit || 'unidades')]))}<h3>Registros por fecha</h3>${table(['Fecha de trabajo','Registros'],byDay.map((item) => [esc(prettyDate(item.work_date || item.date || item.label)),fmt(item.records ?? item.count ?? item.value)]))}</section>`;
    window.LabTables?.enhance(byId('detail-content'));
  }
  function renderOrders() {
    if(current.visitor){byId('detail-content').innerHTML=`${intro()}<p id="detail-total"><strong>${fmt(current.aggregateCount)}</strong> lotes pendientes al ${esc(prettyDate(current.cutoff || today()))}.</p><div class="notice soft">Tu perfil visitante muestra los totales de recepción. Para consultar procesos, órdenes y entregas se requiere un perfil autorizado.</div>`;return;}
    const orders=current.orders || [];
    byId('detail-content').innerHTML=`${intro()}<p id="detail-total"><strong>${fmt(orders.length)}</strong> órdenes en esta selección · estado al ${esc(prettyDate(current.cutoff || today()))}.</p><div id="detail-orders">${table(['Proceso / orden','SAP','Esperado','Recibido','Pendiente','Estado','Abrir'],orders.map((order) => [
      `${esc(order.process)}<small>${esc(order.order_number)}</small>`,esc(order.sap),order.expected===null?'Por confirmar':fmt(order.expected),fmt(order.received),order.pending===null?'Por confirmar':fmt(order.pending),signalBadge(order.signal,orderStateLabel(order)),`<button type="button" class="btn small secondary" data-detail-order="${order.id}">Ver entregas →</button>`]),'No hay órdenes que coincidan con este indicador.')}</div><p class="detail-table-tip">Un número esperado por confirmar no se interpreta como cero. Los excedentes se consultan en la orden y no eliminan pendientes de otra orden.</p>`;
    window.LabTables?.enhance(byId('detail-content'));
  }
  async function renderRecord(ticket) {
    const result=await api(`/api/eventos/${current.recordId}`);if(ticket!==requestNumber || !dialog.open)return;
    const record=result.record;
    byId('detail-title').textContent=record.data?.serie ? `Registro · ${record.data.serie}` : `Registro #${record.id}`;
    byId('detail-content').innerHTML=`<section class="detail-explanation"><h3>Información completa del registro</h3><p>Estos son los datos guardados de esta actividad. Abrir o consultar esta ficha no modifica el historial.</p></section>${detailHtml(record)}${record.traceability?`<section class="detail-explanation"><h3>Trazabilidad del ingreso</h3><dl class="detail-list"><dt>Ingreso</dt><dd>${esc(record.traceability.cycle_number||'Sin serie')}</dd><dt>Repetido justificado</dt><dd>${esc(record.traceability.duplicate_note||'No aplica')}</dd><dt>Motivo de registro delegado</dt><dd>${esc(record.traceability.delegation_reason||'Captura propia')}</dd><dt>Asignación temporal</dt><dd>${esc(record.traceability.assignment_id||'Gestión directa o permiso permanente')}</dd></dl></section>`:''}<div class="detail-record-footer">${history.length?'<button type="button" class="btn secondary" id="detail-record-return">← Volver a la lista</button>':''}<p>Para corregir o anular un registro, utiliza sus acciones en la sección Registros. Cada cambio conserva su motivo y auditoría.</p></div>`;
    if(byId('detail-record-return'))byId('detail-record-return').onclick=() => byId('detail-back').click();
  }
  async function renderOrder(ticket) {
    const result=await api(`/api/ordenes/${current.orderId}`);if(ticket!==requestNumber || !dialog.open)return;
    const order=current.orderSnapshot || result.order,cutoff=current.cutoff || today();
    const records=(result.deliveries || []).filter((record) => record.state==='valido' && record.work_date<=cutoff);
    byId('detail-title').textContent=`Proceso ${order.process}`;
    byId('detail-content').innerHTML=`<section class="detail-explanation"><h3>Entregas de esta orden</h3><p>El saldo corresponde al ${esc(prettyDate(cutoff))}. Se muestran las entregas válidas hasta esa fecha; no se limita por la fecha Desde del resumen.</p><p id="detail-query-summary">Orden ${esc(order.order_number)} · SAP ${esc(order.sap)}${S.user.role==='tecnico'?' · La tabla muestra tus entregas; el saldo de la orden incluye los aportes de todo el equipo.':''}</p></section><dl class="detail-list"><dt>Esperado</dt><dd>${order.expected===null?'Por confirmar':fmt(order.expected)}</dd><dt>Recibido al corte</dt><dd>${fmt(order.received)}</dd><dt>Pendiente al corte</dt><dd>${order.pending===null?'Por confirmar':fmt(order.pending)}</dd><dt>Excedente</dt><dd>${fmt(order.excess || 0)}</dd><dt>Estado al corte</dt><dd>${signalBadge(order.signal,orderStateLabel(order))}</dd></dl><p id="detail-total"><strong>${fmt(records.length)}</strong> entregas visibles para tu cuenta.</p><div id="detail-order-deliveries">${recordTable(records)}</div><div class="detail-record-footer">${history.length?'<button type="button" class="btn secondary" id="detail-order-list-return">← Volver a la lista</button>':''}<button type="button" class="btn secondary" id="detail-order-admin">Consultar estado actual y acciones de la orden</button></div>`;
    if(byId('detail-order-list-return'))byId('detail-order-list-return').onclick=() => byId('detail-back').click();
    byId('detail-order-admin').onclick=() => showOrderDetail(current.orderId).catch((error) => toast(error.message,'error'));
    window.LabTables?.enhance(byId('detail-content'));
  }
  async function render() {
    if(!current || !dialog?.open)return;
    const ticket=++requestNumber;top();loading();
    try {
      if(current.mode==='record')await renderRecord(ticket);
      else if(current.mode==='order')await renderOrder(ticket);
      else if(current.mode==='orders')renderOrders();
      else await renderRecords(ticket);
    } catch(error) {if(ticket===requestNumber && dialog.open)fail(error);}
  }
  async function openRecord(id) {
    if(current)history.push({...current});
    current={mode:'record',recordId:Number(id),title:'Detalle del registro'};
    if(!dialog?.open){ensureDialog();dialog.showModal();}await render();
  }
  async function openOrder(id) {
    const previous=current,order=(previous?.orders || []).find((item) => String(item.id)===String(id));
    if(previous)history.push({...previous});
    current={mode:'order',orderId:id,orderSnapshot:order,cutoff:previous?.cutoff || today(),title:'Entregas de la orden'};
    if(!dialog?.open){ensureDialog();dialog.showModal();}await render();
  }
  async function activate(node) {
    const desc=descriptors.get(node);if(!desc || !ready())return;
    return open(desc);
  }
  function enhance(root=document) {
    if(!ready()){if(dialog?.open)close();return;}
    annotateCards();
    for(const node of root.querySelectorAll?.('.chart-container [data-chart-tooltip][data-value]') || []){
      annotateChart(node);
      if(node.tagName.toLowerCase()==='g' && descriptors.has(node) && !node.querySelector('[data-detail-hit]')){
        const box=node.getBBox();
        if(box.width>0 && box.height>0){
          const hit=document.createElementNS('http://www.w3.org/2000/svg','rect');
          for(const [key,value] of Object.entries({x:box.x,y:box.y,width:box.width,height:box.height,fill:'transparent','pointer-events':'all','aria-hidden':'true','data-detail-hit':'true'}))hit.setAttribute(key,String(value));
          node.prepend(hit);
        }
      }
    }
    for(const tableNode of root.querySelectorAll?.('table') || [])annotateTable(tableNode);
  }
  function queueEnhance() {
    if(scheduled)return;scheduled=true;requestAnimationFrame(() => {scheduled=false;enhance();});
  }
  document.addEventListener('lab:table-before-enhance',(event) => annotateTable(event.detail.table));
  document.addEventListener('click',(event) => {
    const recordButton=event.target.closest?.('[data-detail-record]');
    if(recordButton){event.preventDefault();openRecord(recordButton.dataset.detailRecord);return;}
    const orderButton=event.target.closest?.('[data-detail-order]');
    if(orderButton){event.preventDefault();openOrder(orderButton.dataset.detailOrder);return;}
    const trigger=event.target.closest?.('.detail-trigger');if(!trigger)return;
    const existingAction=event.target.closest?.('button,a,input,select,textarea,summary');
    if(existingAction && existingAction!==trigger)return;
    event.preventDefault();activate(trigger);
  });
  document.addEventListener('keydown',(event) => {
    if(!['Enter',' '].includes(event.key))return;
    const trigger=event.target.closest?.('.detail-trigger');if(!trigger || event.target!==trigger || trigger.matches('button,a,input,select,textarea'))return;
    event.preventDefault();activate(trigger);
  });
  window.LabDetails={enhance,open,close,openRecord,openOrder};
  document.addEventListener('toggle',queueEnhance,true);
  const start=() => {observer=new MutationObserver(queueEnhance);observer.observe(document.body,{childList:true,subtree:true});queueEnhance();};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
})();
