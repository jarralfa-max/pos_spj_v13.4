/**
 * dashboard.js — SPJ POS Web UI
 * Dashboard principal con Apache ECharts.
 * Gráficas: Ventas 7 días, Top Productos, Inventario, Ventas por hora.
 * Todos los colores se leen de las CSS variables para respetar el tema.
 */

/* ── Paleta de colores ECharts desde CSS variables ────────────────────────── */
function getChartColors() {
  const s = getComputedStyle(document.documentElement);
  const g = (v) => s.getPropertyValue(v).trim();
  return {
    primary:   g('--color-primary'),
    success:   g('--color-success'),
    danger:    g('--color-danger'),
    warning:   g('--color-warning'),
    info:      g('--color-info'),
    accent:    g('--color-accent'),
    gridLine:  g('--chart-grid'),
    textColor: g('--chart-text'),
    bg:        g('--chart-bg'),
    series:    [
      g('--color-primary'), g('--color-success'), g('--color-warning'),
      g('--color-info'),    g('--color-accent'),   g('--color-danger'),
    ],
  };
}

/* ── Instancias de charts activas ────────────────────────────────────────── */
const _chartInstances = {};

function _getOrCreate(id) {
  const el = document.getElementById(id);
  if (!el) return null;
  if (_chartInstances[id]) {
    _chartInstances[id].dispose();
    delete _chartInstances[id];
  }
  const chart = echarts.init(el, null, { renderer: 'svg' });
  _chartInstances[id] = chart;
  /* Responsive */
  const ro = new ResizeObserver(() => chart.resize());
  ro.observe(el);
  return chart;
}

/* ── Actualizar tema en todos los charts ─────────────────────────────────── */
function updateTheme(_theme) {
  Object.values(_chartInstances).forEach(c => {
    if (c && !c.isDisposed()) c.resize();
  });
}

/* ── Opciones base compartidas ───────────────────────────────────────────── */
function _baseOpts() {
  const C = getChartColors();
  return {
    backgroundColor: 'transparent',
    textStyle: { fontFamily: "'Inter','Segoe UI',system-ui,sans-serif", color: C.textColor },
    color: C.series,
    grid: { left: 16, right: 16, top: 16, bottom: 0, containLabel: true },
  };
}

/* ════════════════════════════════════════════════════════════════════════════
   GRÁFICA 1 — Ventas de los últimos 7 días (Línea + Barras)
   ════════════════════════════════════════════════════════════════════════════ */

function renderVentasChart(data) {
  const chart = _getOrCreate('chart-ventas');
  if (!chart) return;

  const C = getChartColors();
  const opts = {
    ..._baseOpts(),
    tooltip: {
      trigger: 'axis',
      backgroundColor: C.bg,
      borderColor: C.gridLine,
      textStyle: { color: C.textColor, fontSize: 12 },
      formatter: (params) => {
        let html = `<b>${params[0].axisValue}</b><br>`;
        params.forEach(p => {
          html += `${p.marker} ${p.seriesName}: <b>${Fmt.money(p.value)}</b><br>`;
        });
        return html;
      },
    },
    legend: {
      data: ['Ventas', 'Pedidos WhatsApp'],
      textStyle: { color: C.textColor, fontSize: 11 },
      bottom: 0,
    },
    xAxis: {
      type: 'category',
      data: data.labels,
      axisLine:   { lineStyle: { color: C.gridLine } },
      axisLabel:  { color: C.textColor, fontSize: 11 },
      axisTick:   { show: false },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: C.gridLine, type: 'dashed' } },
      axisLabel: { color: C.textColor, fontSize: 11,
                   formatter: v => v >= 1000 ? `$${(v/1000).toFixed(1)}k` : `$${v}` },
    },
    series: [
      {
        name: 'Ventas',
        type: 'bar',
        data: data.ventas,
        barMaxWidth: 40,
        itemStyle: { borderRadius: [4, 4, 0, 0], color: C.primary },
        emphasis: { itemStyle: { color: C.accent } },
      },
      {
        name: 'Pedidos WhatsApp',
        type: 'line',
        data: data.pedidos_wa,
        smooth: true,
        symbol: 'circle',
        symbolSize: 6,
        lineStyle: { color: C.success, width: 2 },
        itemStyle: { color: C.success },
        areaStyle: { color: { type:'linear', x:0,y:0,x2:0,y2:1,
          colorStops:[{offset:0, color: C.success+'40'},{offset:1, color: C.success+'00'}]}},
      },
    ],
  };
  chart.setOption(opts);
}

/* ════════════════════════════════════════════════════════════════════════════
   GRÁFICA 2 — Top 10 Productos más vendidos (Barras horizontales)
   ════════════════════════════════════════════════════════════════════════════ */

function renderProductosChart(data) {
  const chart = _getOrCreate('chart-productos');
  if (!chart) return;

  const C = getChartColors();
  /* Ordenar de mayor a menor para barras horizontales */
  const sorted = [...data].sort((a, b) => a.ventas - b.ventas);

  chart.setOption({
    ..._baseOpts(),
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      backgroundColor: C.bg,
      borderColor: C.gridLine,
      textStyle: { color: C.textColor, fontSize: 12 },
      formatter: (params) => {
        const p = params[0];
        return `<b>${p.name}</b><br>${p.marker} ${Fmt.money(p.value)} vendidos`;
      },
    },
    grid: { left: 8, right: 16, top: 8, bottom: 8, containLabel: true },
    xAxis: {
      type: 'value',
      axisLabel: { color: C.textColor, fontSize: 10,
                   formatter: v => v >= 1000 ? `$${(v/1000).toFixed(0)}k` : `$${v}` },
      splitLine: { lineStyle: { color: C.gridLine, type: 'dashed' } },
    },
    yAxis: {
      type: 'category',
      data: sorted.map(d => d.nombre),
      axisLabel: { color: C.textColor, fontSize: 11, width: 120, overflow: 'truncate' },
      axisTick:  { show: false },
      axisLine:  { lineStyle: { color: C.gridLine } },
    },
    series: [{
      type: 'bar',
      data: sorted.map((d, i) => ({
        value: d.ventas,
        itemStyle: {
          borderRadius: [0, 4, 4, 0],
          color: C.series[i % C.series.length],
        },
      })),
      barMaxWidth: 24,
      label: {
        show: true, position: 'right',
        formatter: (p) => Fmt.money(p.value),
        color: C.textColor, fontSize: 10,
      },
    }],
  });
}

/* ════════════════════════════════════════════════════════════════════════════
   GRÁFICA 3 — Inventario por categoría (Donut)
   ════════════════════════════════════════════════════════════════════════════ */

function renderInventarioChart(data) {
  const chart = _getOrCreate('chart-inventario');
  if (!chart) return;

  const C = getChartColors();
  chart.setOption({
    ..._baseOpts(),
    tooltip: {
      trigger: 'item',
      backgroundColor: C.bg,
      borderColor: C.gridLine,
      textStyle: { color: C.textColor, fontSize: 12 },
      formatter: '{b}: <b>{c} unidades</b> ({d}%)',
    },
    legend: {
      orient: 'vertical',
      right: 8,
      top: 'center',
      textStyle: { color: C.textColor, fontSize: 11 },
      formatter: (name) => {
        const item = data.find(d => d.categoria === name);
        return `${name}  ${item ? item.unidades : 0}`;
      },
    },
    series: [{
      type: 'pie',
      radius: ['45%', '70%'],
      center: ['38%', '50%'],
      data: data.map((d, i) => ({
        name: d.categoria,
        value: d.unidades,
        itemStyle: { color: C.series[i % C.series.length] },
      })),
      label: { show: false },
      emphasis: {
        label: { show: true, fontSize: 13, fontWeight: 'bold', color: C.textColor },
        itemStyle: { shadowBlur: 10, shadowOffsetX: 0, shadowColor: 'rgba(0,0,0,0.3)' },
      },
    }],
  });
}

/* ════════════════════════════════════════════════════════════════════════════
   GRÁFICA 4 — Ventas por hora del día (Heatmap / Barras)
   ════════════════════════════════════════════════════════════════════════════ */

function renderVentasHoraChart(data) {
  const chart = _getOrCreate('chart-ventas-hora');
  if (!chart) return;

  const C = getChartColors();
  const maxVal = Math.max(...data.map(d => d.ventas), 1);

  chart.setOption({
    ..._baseOpts(),
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      backgroundColor: C.bg,
      borderColor: C.gridLine,
      textStyle: { color: C.textColor, fontSize: 12 },
      formatter: (params) => {
        const p = params[0];
        return `<b>${p.axisValue}:00 hrs</b><br>${p.marker} ${Fmt.money(p.value)}`;
      },
    },
    xAxis: {
      type: 'category',
      data: data.map(d => `${d.hora}`),
      axisLabel: { color: C.textColor, fontSize: 10,
                   formatter: v => `${v}h` },
      axisTick:  { show: false },
      axisLine:  { lineStyle: { color: C.gridLine } },
    },
    yAxis: {
      type: 'value',
      show: false,
    },
    series: [{
      type: 'bar',
      data: data.map(d => ({
        value: d.ventas,
        itemStyle: {
          borderRadius: [3, 3, 0, 0],
          color: {
            type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: C.info },
              { offset: 1, color: C.primary },
            ],
          },
          opacity: 0.4 + 0.6 * (d.ventas / maxVal),
        },
      })),
      barMaxWidth: 28,
    }],
  });
}

/* ════════════════════════════════════════════════════════════════════════════
   GRÁFICA 5 — Tendencia de caja (Área)
   ════════════════════════════════════════════════════════════════════════════ */

function renderTendenciaCajaChart(data) {
  const chart = _getOrCreate('chart-caja');
  if (!chart) return;

  const C = getChartColors();
  chart.setOption({
    ..._baseOpts(),
    tooltip: {
      trigger: 'axis',
      backgroundColor: C.bg,
      borderColor: C.gridLine,
      textStyle: { color: C.textColor, fontSize: 12 },
      formatter: (params) => {
        let html = `<b>${params[0].axisValue}</b><br>`;
        params.forEach(p => {
          html += `${p.marker} ${p.seriesName}: <b>${Fmt.money(p.value)}</b><br>`;
        });
        return html;
      },
    },
    legend: {
      data: ['Ingresos', 'Egresos', 'Saldo'],
      textStyle: { color: C.textColor, fontSize: 11 },
      bottom: 0,
    },
    xAxis: {
      type: 'category',
      data: data.labels,
      axisLine:  { lineStyle: { color: C.gridLine } },
      axisLabel: { color: C.textColor, fontSize: 10 },
      axisTick:  { show: false },
      boundaryGap: false,
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: C.gridLine, type: 'dashed' } },
      axisLabel: { color: C.textColor, fontSize: 10,
                   formatter: v => v >= 1000 ? `$${(v/1000).toFixed(1)}k` : `$${v}` },
    },
    series: [
      {
        name: 'Ingresos',
        type: 'line', smooth: true, symbol: 'none',
        data: data.ingresos,
        lineStyle: { color: C.success, width: 2 },
        areaStyle: { color: { type:'linear', x:0,y:0,x2:0,y2:1,
          colorStops:[{offset:0,color:C.success+'50'},{offset:1,color:C.success+'00'}]}},
      },
      {
        name: 'Egresos',
        type: 'line', smooth: true, symbol: 'none',
        data: data.egresos,
        lineStyle: { color: C.danger, width: 2 },
        areaStyle: { color: { type:'linear', x:0,y:0,x2:0,y2:1,
          colorStops:[{offset:0,color:C.danger+'30'},{offset:1,color:C.danger+'00'}]}},
      },
      {
        name: 'Saldo',
        type: 'line', smooth: true, symbol: 'circle', symbolSize: 5,
        data: data.saldo,
        lineStyle: { color: C.primary, width: 2 },
        itemStyle: { color: C.primary },
      },
    ],
  });
}


/* ════════════════════════════════════════════════════════════════════════════
   CARGA DEL DASHBOARD COMPLETO
   ════════════════════════════════════════════════════════════════════════════ */

async function loadDashboard(container, periodo = 'hoy') {
  showLoader(container, 'Cargando dashboard...');

  /* Cargar todo en paralelo */
  const [kpisRes, ventasRes, productosRes, inventarioRes] = await Promise.allSettled([
    API.dashboard.kpis({ periodo }),
    API.dashboard.ventasChart({ periodo }),
    API.dashboard.productosTop({ periodo }),
    API.dashboard.inventario(),
  ]);

  const kpis       = kpisRes.status === 'fulfilled'      ? kpisRes.value      : null;
  const ventas     = ventasRes.status === 'fulfilled'     ? ventasRes.value    : null;
  const productos  = productosRes.status === 'fulfilled'  ? productosRes.value : null;
  const inventario = inventarioRes.status === 'fulfilled' ? inventarioRes.value: null;

  container.innerHTML = _buildDashboardHTML(periodo);

  /* KPI Cards */
  _renderKpis(kpis);

  /* Charts (necesitan que el DOM exista) */
  if (ventas)     renderVentasChart(ventas);
  if (productos && productos.items)  renderProductosChart(productos.items);
  if (inventario && inventario.categorias) renderInventarioChart(inventario.categorias);
  if (ventas && ventas.por_hora)  renderVentasHoraChart(ventas.por_hora);
  if (ventas && ventas.caja)      renderTendenciaCajaChart(ventas.caja);

  /* Tabla de últimas ventas */
  if (kpis && kpis.ultimas_ventas) {
    _renderUltimasVentas(kpis.ultimas_ventas);
  }

  /* Alertas */
  if (kpis && kpis.alertas) _renderAlertas(kpis.alertas);

  /* Bind filtros */
  document.getElementById('periodo-select')?.addEventListener('change', (e) => {
    loadDashboard(container, e.target.value);
  });
  document.getElementById('btn-refresh')?.addEventListener('click', () => {
    loadDashboard(container, periodo);
  });
}

/* ── HTML del dashboard ──────────────────────────────────────────────────── */
function _buildDashboardHTML(periodo) {
  return `
  <div class="dashboard-grid fade-in">

    <!-- Header -->
    <div class="page-header">
      <div>
        <h1 class="page-title">Dashboard</h1>
        <p class="page-subtitle">Inteligencia Comercial · SPJ POS</p>
      </div>
      <div class="page-actions">
        <div class="conn-status" id="conn-status">
          <span class="status-dot online"></span>
          Conectado
        </div>
        <select class="form-select" id="periodo-select" style="width:140px">
          <option value="hoy"       ${periodo==='hoy'       ?'selected':''}>Hoy</option>
          <option value="semana"    ${periodo==='semana'    ?'selected':''}>Esta semana</option>
          <option value="mes"       ${periodo==='mes'       ?'selected':''}>Este mes</option>
          <option value="trimestre" ${periodo==='trimestre' ?'selected':''}>Trimestre</option>
        </select>
        <button class="btn btn-secondary" id="btn-refresh" data-tooltip="Actualizar datos">
          ↺ Refrescar
        </button>
      </div>
    </div>

    <!-- Alertas -->
    <div id="alertas-container"></div>

    <!-- KPIs -->
    <div class="kpi-grid" id="kpi-grid">
      ${_kpiSkeleton(4)}
    </div>

    <!-- Charts row 1: Ventas + Productos Top -->
    <div class="charts-row">
      <div class="chart-card">
        <div class="chart-header">
          <div>
            <div class="chart-title">📈 Ventas del período</div>
            <div class="chart-subtitle">Ventas vs Pedidos WhatsApp</div>
          </div>
        </div>
        <div class="chart-body">
          <div id="chart-ventas" class="chart-container" style="height:260px"></div>
        </div>
      </div>

      <div class="chart-card">
        <div class="chart-header">
          <div>
            <div class="chart-title">🏆 Top Productos</div>
            <div class="chart-subtitle">Por monto vendido</div>
          </div>
        </div>
        <div class="chart-body">
          <div id="chart-productos" class="chart-container" style="height:260px"></div>
        </div>
      </div>
    </div>

    <!-- Charts row 2: Inventario + Ventas por hora -->
    <div class="charts-row">
      <div class="chart-card">
        <div class="chart-header">
          <div>
            <div class="chart-title">📦 Inventario por categoría</div>
            <div class="chart-subtitle">Distribución en unidades</div>
          </div>
        </div>
        <div class="chart-body">
          <div id="chart-inventario" class="chart-container" style="height:240px"></div>
        </div>
      </div>

      <div class="chart-card">
        <div class="chart-header">
          <div>
            <div class="chart-title">⏰ Ventas por hora</div>
            <div class="chart-subtitle">Distribución horaria hoy</div>
          </div>
        </div>
        <div class="chart-body">
          <div id="chart-ventas-hora" class="chart-container" style="height:240px"></div>
        </div>
      </div>
    </div>

    <!-- Chart row 3: Tendencia caja (full width) -->
    <div class="chart-card">
      <div class="chart-header">
        <div>
          <div class="chart-title">💰 Flujo de Caja</div>
          <div class="chart-subtitle">Ingresos · Egresos · Saldo acumulado</div>
        </div>
      </div>
      <div class="chart-body">
        <div id="chart-caja" class="chart-container" style="height:220px"></div>
      </div>
    </div>

    <!-- Últimas ventas -->
    <div class="card">
      <div class="card-header">
        <div>
          <div class="card-title">🧾 Últimas Ventas</div>
          <div class="card-subtitle">Transacciones recientes del período</div>
        </div>
        <button class="btn btn-sm btn-outline-primary" onclick="Router.navigate('ventas')">Ver todas →</button>
      </div>
      <div class="card-body" id="ultimas-ventas-container">
        ${_tableSkeleton(5, 5)}
      </div>
    </div>

  </div>`;
}

/* ── Render KPIs ─────────────────────────────────────────────────────────── */
function _renderKpis(data) {
  const el = document.getElementById('kpi-grid');
  if (!el) return;

  if (!data) {
    el.innerHTML = `<div class="alert alert-warning" style="grid-column:1/-1">
      No se pudo cargar datos del servidor. Verifica la conexión.</div>`;
    return;
  }

  el.innerHTML = [
    buildKpiCard({ label:'Ventas del día',       value: Fmt.money(data.ventas_hoy),
                   delta: data.ventas_delta,     icon: '💵', color: 'primary' }),
    buildKpiCard({ label:'Tickets emitidos',     value: Fmt.number(data.tickets_hoy),
                   delta: data.tickets_delta,    icon: '🧾', color: 'success' }),
    buildKpiCard({ label:'Ticket promedio',      value: Fmt.money(data.ticket_promedio),
                   delta: data.promedio_delta,   icon: '📊', color: 'info' }),
    buildKpiCard({ label:'Clientes activos',     value: Fmt.number(data.clientes_activos),
                   delta: data.clientes_delta,   icon: '👥', color: 'accent' }),
    buildKpiCard({ label:'Stock bajo mínimo',    value: Fmt.number(data.stock_bajo),
                   delta: null,                  icon: '⚠️', color: 'warning' }),
    buildKpiCard({ label:'Pedidos WhatsApp',     value: Fmt.number(data.pedidos_wa),
                   delta: data.pedidos_wa_delta, icon: '💬', color: 'success' }),
    buildKpiCard({ label:'Merma del día',        value: Fmt.money(data.merma_hoy),
                   delta: data.merma_delta,      icon: '🗑️', color: 'danger' }),
    buildKpiCard({ label:'Margen bruto',         value: Fmt.percent(data.margen_bruto),
                   delta: data.margen_delta,     icon: '📈', color: 'primary' }),
  ].join('');
}

/* ── Render últimas ventas ───────────────────────────────────────────────── */
function _renderUltimasVentas(rows) {
  const el = document.getElementById('ultimas-ventas-container');
  if (!el || !rows.length) return;

  DataTable({
    container: el,
    pageSize: 8,
    columns: [
      { key: 'folio',    label: 'Folio',    class: 'font-medium' },
      { key: 'fecha',    label: 'Fecha',    render: v => Fmt.datetime(v) },
      { key: 'cliente',  label: 'Cliente' },
      { key: 'cajero',   label: 'Cajero' },
      { key: 'forma_pago', label: 'Pago',
        render: v => `<span class="badge badge-default">${v || '—'}</span>` },
      { key: 'total',    label: 'Total',    align: 'right',
        render: v => `<strong>${Fmt.money(v)}</strong>` },
      { key: 'estado',   label: 'Estado',
        render: v => {
          const map = { completada:'success', cancelada:'danger', pendiente:'warning' };
          return `<span class="badge badge-${map[v]||'default'} badge-dot">${v||'—'}</span>`;
        }},
    ],
    rows,
  });
}

/* ── Render alertas ──────────────────────────────────────────────────────── */
function _renderAlertas(alertas) {
  const el = document.getElementById('alertas-container');
  if (!el || !alertas.length) return;

  const typeMap = { critica:'danger', alta:'warning', media:'info', baja:'info' };
  el.innerHTML = alertas.slice(0, 3).map(a => `
    <div class="alert alert-${typeMap[a.prioridad]||'info'} fade-in">
      <div class="flex items-center gap-2 flex-1">
        <strong>${a.titulo}</strong> — ${a.mensaje}
      </div>
    </div>`).join('');
}

/* ── Skeletons ───────────────────────────────────────────────────────────── */
function _kpiSkeleton(n) {
  return Array.from({length:n}, () =>
    `<div class="kpi-card"><div class="skeleton" style="height:80px"></div></div>`
  ).join('');
}
function _tableSkeleton(rows, cols) {
  const cells = Array.from({length:cols}, () =>
    `<td><div class="skeleton" style="height:14px;border-radius:4px"></div></td>`
  ).join('');
  const body = Array.from({length:rows}, () => `<tr>${cells}</tr>`).join('');
  return `<div class="table-container"><table class="table"><tbody>${body}</tbody></table></div>`;
}


/* ── Export para el namespace global ────────────────────────────────────── */
window.SPJCharts = { updateTheme, loadDashboard };
window.loadDashboard = loadDashboard;
