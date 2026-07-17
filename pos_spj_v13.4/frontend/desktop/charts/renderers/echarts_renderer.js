/* SPJ ECharts renderer (FASE DS-5).
 *
 * Consumes the payload built by chart_bridge.build_chart_payload and renders it
 * with Apache ECharts. Colors, axis and tooltip styling come from payload.theme
 * / payload.palette (assigned from the JUANIS theme in Python) — never hardcoded
 * here. Supports the canonical chart types.
 */
(function (global) {
  "use strict";

  function baseTextStyle(theme) {
    return { color: theme.text, fontFamily: "Segoe UI, Inter, sans-serif" };
  }

  function tooltip(theme) {
    return {
      trigger: "axis",
      backgroundColor: theme.tooltipBg,
      borderColor: theme.axis,
      textStyle: { color: theme.tooltipText }
    };
  }

  function axisCommon(theme) {
    return {
      axisLine: { lineStyle: { color: theme.axis } },
      axisLabel: { color: theme.mutedText },
      splitLine: { lineStyle: { color: theme.grid } }
    };
  }

  function markLines(annotations) {
    if (!annotations || !annotations.length) return undefined;
    return {
      symbol: "none",
      data: annotations.map(function (a) {
        return { yAxis: a.value, name: a.label };
      })
    };
  }

  function seriesType(chartType, override) {
    if (override) return override;
    switch (chartType) {
      case "line": case "area": case "stacked_area": return "line";
      case "bar": case "horizontal_bar": case "stacked_bar": case "waterfall":
        return "bar";
      case "donut": case "pie": return "pie";
      case "scatter": return "scatter";
      case "gauge": return "gauge";
      case "heatmap": return "heatmap";
      case "funnel": return "funnel";
      case "timeline": return "line";
      case "combo": return "bar";
      default: return "line";
    }
  }

  function buildCartesian(p) {
    var t = p.chartType;
    var horizontal = t === "horizontal_bar";
    var stacked = t === "stacked_bar" || t === "stacked_area";
    var isArea = t === "area" || t === "stacked_area";
    var series = p.series.map(function (s, i) {
      var st = seriesType(t, s.type);
      var item = {
        name: s.name,
        type: st,
        data: s.data,
        itemStyle: { color: s.color },
        markLine: i === 0 ? markLines(p.annotations) : undefined
      };
      if (st === "line" && isArea) item.areaStyle = {};
      if (stacked) item.stack = s.stack || "total";
      return item;
    });
    var category = { type: "category", data: p.categories };
    var value = { type: "value" };
    return {
      color: p.palette,
      textStyle: baseTextStyle(p.theme),
      tooltip: tooltip(p.theme),
      legend: { textStyle: { color: p.theme.mutedText } },
      grid: { left: 48, right: 24, top: 40, bottom: 32, containLabel: true },
      xAxis: Object.assign({}, horizontal ? value : category, axisCommon(p.theme)),
      yAxis: Object.assign({}, horizontal ? category : value, axisCommon(p.theme)),
      series: series
    };
  }

  function buildPie(p) {
    var donut = p.chartType === "donut";
    var data = p.categories.map(function (c, i) {
      var s = p.series[0];
      return { name: c, value: s ? s.data[i] : 0,
               itemStyle: { color: p.palette[i % p.palette.length] } };
    });
    return {
      textStyle: baseTextStyle(p.theme),
      tooltip: { trigger: "item", backgroundColor: p.theme.tooltipBg,
                 textStyle: { color: p.theme.tooltipText } },
      legend: { textStyle: { color: p.theme.mutedText } },
      series: [{ type: "pie", radius: donut ? ["45%", "70%"] : "70%", data: data }]
    };
  }

  function buildGauge(p) {
    var s = p.series[0];
    var value = s && s.data.length ? s.data[s.data.length - 1] : 0;
    return {
      textStyle: baseTextStyle(p.theme),
      series: [{ type: "gauge", progress: { show: true },
                 detail: { valueAnimation: true, color: p.theme.text },
                 data: [{ value: value, name: p.title }] }]
    };
  }

  function buildFunnel(p) {
    var data = p.categories.map(function (c, i) {
      var s = p.series[0];
      return { name: c, value: s ? s.data[i] : 0 };
    });
    return {
      color: p.palette,
      textStyle: baseTextStyle(p.theme),
      tooltip: { trigger: "item", backgroundColor: p.theme.tooltipBg,
                 textStyle: { color: p.theme.tooltipText } },
      series: [{ type: "funnel", data: data }]
    };
  }

  function buildOption(p) {
    switch (p.chartType) {
      case "pie": case "donut": return buildPie(p);
      case "gauge": return buildGauge(p);
      case "funnel": return buildFunnel(p);
      default: return buildCartesian(p);
    }
  }

  function render(el, payload) {
    if (payload.state && payload.state !== "READY" && payload.state !== "STALE") {
      el.parentNode.querySelector("#fallback").hidden = false;
      el.parentNode.querySelector("#fallback").textContent =
        payload.emptyMessage || "Sin datos para mostrar";
      return null;
    }
    var chart = global.echarts.init(el, null, { renderer: "canvas" });
    chart.setOption(buildOption(payload));
    global.addEventListener("resize", function () { chart.resize(); });
    return chart;
  }

  global.SPJChart = { render: render, buildOption: buildOption };
})(window);
