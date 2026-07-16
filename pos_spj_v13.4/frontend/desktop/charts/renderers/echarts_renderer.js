(function () {
  const payload = window.SPJ_CHART_PAYLOAD || {};
  const root = document.getElementById('chart-root');

  function toSeries(series) {
    return (series || []).map(function (item) {
      return {
        name: item.name,
        type: item.series_type === 'horizontal_bar' ? 'bar' : item.series_type,
        stack: item.stack_group || undefined,
        data: item.values || []
      };
    });
  }

  function renderFallback() {
    if (!root) {
      return;
    }
    const title = document.createElement('h2');
    title.textContent = payload.title || 'Gráfica';
    const summary = document.createElement('p');
    summary.textContent = payload.accessibility_summary || payload.empty_message || 'Datos disponibles en tabla alternativa.';
    root.appendChild(title);
    root.appendChild(summary);
  }

  function renderECharts() {
    if (!root || typeof echarts === 'undefined') {
      renderFallback();
      return;
    }
    const chart = echarts.init(root);
    chart.setOption({
      title: { text: payload.title || '', subtext: payload.subtitle || '' },
      tooltip: { trigger: 'axis' },
      legend: { type: 'scroll' },
      xAxis: { type: 'category', data: payload.categories || [] },
      yAxis: { type: 'value', name: payload.unit || payload.currency_code || '' },
      series: toSeries(payload.series)
    });
    window.addEventListener('resize', function () { chart.resize(); });
  }

  renderECharts();
}());
