# Vendored chart library — Apache ECharts

The chart subsystem renders with **Apache ECharts**, loaded as an **offline,
vendored** asset (the desktop app has no CDN access, and the UI/UX skill forbids
external requests). Drop the minified library here:

```
frontend/desktop/charts/vendor/echarts.min.js
```

- Version: pin a specific ECharts 5.x release and record it in this file.
- Source: the official Apache ECharts distribution (`echarts.min.js`).
- License: Apache-2.0.

`chart_base.html` references `../vendor/echarts.min.js` relative to the template,
and `HtmlChartView` loads the template with a `baseUrl` at the charts directory so
this path resolves without network access.

If `echarts.min.js` is absent, `HtmlChartView` still works: it falls back to the
accessible **tabular alternative** (the same table used for screen readers), so
the app degrades gracefully instead of showing a blank chart.
