"""Chart rendering layer (FASE DS-5).

QueryService → ChartDataDTO → chart_bridge (assigns theme palette) → HtmlChartView
→ chart_base.html → echarts_renderer.js → Apache ECharts. Colors come only from
the theme here; the DTO stays color-free.
"""
