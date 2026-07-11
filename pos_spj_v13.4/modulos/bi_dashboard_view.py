# -*- coding: utf-8 -*-
"""Renderer del dashboard ejecutivo BI a HTML autónomo (offline, sin CDN).

Transforma el `DashboardPayload` (dict) del BiDashboardService en una página
HTML/SVG lista para mostrarse en un QWebEngineView. Es Python puro y testeable
(no importa PyQt). Estilo oscuro estándar del módulo: tarjetas #1E293B, acentos
azul/dorado, KPIs prominentes, columna lateral de highlights/alertas/insights.
"""
from __future__ import annotations

from html import escape
from typing import Any

from modulos import bi_theme
from modulos.bi_charts import _bar_svg, _donut_svg, _hbar_svg, _line_svg

# Colores derivados de los design tokens globales (sin hex hardcodeado).
_BG = bi_theme.BG
_CARD = bi_theme.CARD
_BORDER = bi_theme.BORDER
_FG = bi_theme.TEXT
_MUTED = bi_theme.MUTED
_POS = bi_theme.ROLE["positive"]
_NEG = bi_theme.ROLE["negative"]
_NEU = bi_theme.ROLE["neutral"]
_GOLD = bi_theme.ROLE["secondary"]
_c = bi_theme.color


def _fmt_value(value: float, unit: str) -> str:
    try:
        value = float(value or 0)
    except Exception:
        value = 0.0
    if unit == "%":
        return f"{value:.2f}%"
    if unit == "x":
        return f"{value:.2f}x"
    if unit == "":
        return f"{int(round(value)):,}"
    # currency
    if value == int(value):
        return f"${int(value):,}"
    return f"${value:,.2f}"


def _delta_html(kpi: dict) -> str:
    direction = kpi.get("direction", "flat")
    semantic = kpi.get("semantic", "neutral")
    color = {"positive": _POS, "negative": _NEG}.get(semantic, _NEU)
    arrow = {"up": "▲", "down": "▼"}.get(direction, "—")
    dp = kpi.get("delta_pct")
    pts = kpi.get("delta_points")
    if dp is not None:
        txt = f"{abs(dp):.1f}% vs anterior"
    elif pts is not None:
        txt = f"{abs(pts):.2f} pp vs anterior"
    else:
        txt = "sin comparativo"
    return (f"<div style='color:{color};font-size:11px;margin-top:4px;'>"
            f"{arrow} {escape(txt)}</div>")


def _kpi_card(kpi: dict) -> str:
    title = escape(str(kpi.get("title", "")))
    tooltip = escape(str(kpi.get("formula", "") or kpi.get("tooltip", "")))
    value = _fmt_value(kpi.get("value", 0), kpi.get("unit", ""))
    drill = str(kpi.get("drilldown", "") or "")
    cursor = "cursor:pointer;" if drill else ""
    hint = " · clic para detalle" if drill else ""
    card = (
        f"<div title='{tooltip}{hint}' style='background:{_CARD};border:1px solid {_BORDER};"
        f"border-radius:10px;padding:12px 14px;min-width:150px;flex:1;{cursor}'>"
        f"<div style='color:{_MUTED};font-size:10px;font-weight:700;"
        f"letter-spacing:.5px;text-transform:uppercase;'>{title}</div>"
        f"<div style='color:{_FG};font-size:22px;font-weight:700;margin-top:6px;'>{value}</div>"
        f"{_delta_html(kpi)}</div>"
    )
    if drill:
        return (f"<a href='spjdrill:{escape(drill)}' "
                "style='text-decoration:none;flex:1;display:flex;'>" + card + "</a>")
    return card


def _chart_svg_from_payload(chart: dict) -> str:
    kind = chart.get("kind", "bar")
    title = chart.get("title", "")
    labels = chart.get("labels", [])
    series = chart.get("series", [])
    prefix = "" if chart.get("unit") == "" else "$"
    if kind == "line":
        svg_series = [(s.get("name", ""), s.get("values", []),
                       s.get("color", "#3b82f6")) for s in series]
        return _line_svg(title, labels, svg_series, prefix)
    values = series[0].get("values", []) if series else []
    color = _c(series[0].get("color", "primary")) if series else _c("primary")
    if kind == "hbar":
        return _hbar_svg(title, labels, values, prefix, color)
    if kind == "donut":
        return _donut_svg(title, labels, values, prefix)
    return _bar_svg(title, labels, values, prefix, color)


def _chart_card(chart: dict) -> str:
    return (f"<div style='background:{_CARD};border:1px solid {_BORDER};"
            "border-radius:10px;padding:8px;'>" + _chart_svg_from_payload(chart) + "</div>")


def _drill_wrap(html: str, drill: str) -> str:
    """Envuelve un bloque en un enlace de drill-down si hay sección destino."""
    drill = str(drill or "")
    if not drill:
        return html
    return (f"<a href='spjdrill:{escape(drill)}' "
            "style='text-decoration:none;display:block;cursor:pointer;'>" + html + "</a>")


def _highlight_card(h: dict) -> str:
    title = escape(str(h.get("title", "")))
    name = escape(str(h.get("name", "")))
    value = _fmt_value(h.get("value", 0), h.get("unit", "$"))
    share = h.get("share_pct", 0)
    card = (
        f"<div style='background:{_CARD};border:1px solid {_BORDER};border-radius:10px;"
        "padding:10px 12px;margin-bottom:8px;'>"
        f"<div style='color:{_GOLD};font-size:10px;font-weight:700;text-transform:uppercase;'>{title}</div>"
        f"<div style='color:{_FG};font-size:15px;font-weight:700;margin-top:2px;'>{name}</div>"
        f"<div style='color:{_MUTED};font-size:12px;'>{value} · {share:.1f}% del total</div></div>"
    )
    return _drill_wrap(card, h.get("drilldown", ""))


def _alert_item(a: dict) -> str:
    color = {"critical": _NEG, "warning": _GOLD}.get(a.get("level"), _MUTED)
    title = escape(str(a.get("title", "")))
    detail = escape(str(a.get("detail", "")))
    return (f"<div style='border-left:3px solid {color};padding:6px 10px;margin-bottom:6px;'>"
            f"<div style='color:{_FG};font-size:12px;font-weight:700;'>⚠ {title}</div>"
            f"<div style='color:{_MUTED};font-size:11px;'>{detail}</div></div>")


def _insight_item(i: dict) -> str:
    title = escape(str(i.get("title", "")))
    detail = escape(str(i.get("detail", "")))
    item = (f"<div style='padding:5px 0;border-bottom:1px solid {_BORDER};'>"
            f"<div style='color:{_FG};font-size:12px;'>• {title}</div>"
            f"<div style='color:{_MUTED};font-size:11px;margin-left:10px;'>{detail}</div></div>")
    return _drill_wrap(item, i.get("drilldown", ""))


def _prediction_card(pred: dict) -> str:
    if not pred:
        return ""
    title = escape(str(pred.get("title", "")))
    value = _fmt_value(pred.get("value", 0), pred.get("unit", "$"))
    detail = escape(str(pred.get("detail", "")))
    return (
        f"<div style='background:{_CARD};border:1px solid {_BORDER};border-radius:10px;"
        "padding:10px 12px;margin-bottom:8px;'>"
        f"<div style='color:{_POS};font-size:10px;font-weight:700;text-transform:uppercase;'>{title}</div>"
        f"<div style='color:{_FG};font-size:18px;font-weight:700;'>{value}</div>"
        f"<div style='color:{_MUTED};font-size:11px;'>{detail}</div></div>"
    )


# Orden de charts en la grilla principal (los que existan en el payload).
_CHART_ORDER = ("sales_trend", "branch_sales", "top_products", "categories",
                "payment_methods", "peak_hours", "forecast", "profitability")


def render_dashboard_html(payload: dict) -> str:
    """Construye el dashboard ejecutivo completo desde el payload (dict)."""
    kpis = payload.get("kpis", [])
    charts = payload.get("charts", {})
    highlights = payload.get("highlights", {})
    alerts = payload.get("alerts", [])
    insights = payload.get("insights", [])
    predictions = payload.get("predictions", {})

    kpi_row = "".join(_kpi_card(k) for k in kpis)
    chart_cards = "".join(_chart_card(charts[k]) for k in _CHART_ORDER if k in charts)

    side = []
    for key in ("top_product", "top_category", "top_branch"):
        if key in highlights:
            side.append(_highlight_card(highlights[key]))
    if predictions.get("next_week"):
        side.append(_prediction_card(predictions["next_week"]))
    if alerts:
        side.append(f"<div style='color:{_GOLD};font-size:11px;font-weight:700;"
                    "text-transform:uppercase;margin:6px 0 4px;'>Alertas BI</div>")
        side.extend(_alert_item(a) for a in alerts)
    if insights:
        side.append(f"<div style='color:{_MUTED};font-size:11px;font-weight:700;"
                    "text-transform:uppercase;margin:8px 0 4px;'>Insights clave</div>")
        side.extend(_insight_item(i) for i in insights)
    sidebar = "".join(side)

    return (
        "<html><head><meta charset='utf-8'>"
        f"<style>html,body{{margin:0;background:{_BG};color:{_FG};"
        "font-family:Inter,Arial,sans-serif;}svg{display:block;width:100%;height:100%;}"
        "*{box-sizing:border-box;}</style></head><body>"
        "<div style='padding:12px;'>"
        # KPI row
        f"<div style='display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px;'>{kpi_row}</div>"
        # main + sidebar
        "<div style='display:grid;grid-template-columns:minmax(0,3fr) minmax(220px,1fr);gap:12px;'>"
        "<div style='display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));'>"
        f"{chart_cards}</div>"
        f"<div>{sidebar}</div>"
        "</div></div></body></html>"
    )


# ── Vistas de secciones detalladas (FASE 8) ───────────────────────────────────

def _mini_kpi(k: dict) -> str:
    title = escape(str(k.get("title", "")))
    value = _fmt_value(k.get("value", 0), k.get("unit", "$"))
    return (f"<div style='background:{_CARD};border:1px solid {_BORDER};border-radius:10px;"
            "padding:10px 14px;min-width:130px;flex:1;'>"
            f"<div style='color:{_MUTED};font-size:10px;font-weight:700;"
            f"text-transform:uppercase;'>{title}</div>"
            f"<div style='color:{_FG};font-size:20px;font-weight:700;margin-top:4px;'>{value}</div></div>")


def _table_card(tbl: dict) -> str:
    title = escape(str(tbl.get("title", "")))
    cols = tbl.get("columns", [])
    rows = tbl.get("rows", [])
    head = "".join(f"<th style='text-align:left;padding:6px 8px;color:{_MUTED};"
                   f"border-bottom:1px solid {_BORDER};font-size:11px;'>{escape(str(c))}</th>"
                   for c in cols)
    body = ""
    if rows:
        for r in rows:
            tds = "".join(f"<td style='padding:5px 8px;color:{_FG};font-size:12px;"
                          f"border-bottom:1px solid {_BORDER};'>{escape(str(v))}</td>" for v in r)
            body += f"<tr>{tds}</tr>"
    else:
        body = (f"<tr><td colspan='{max(1,len(cols))}' style='padding:10px;color:{_MUTED};"
                "font-size:12px;'>Sin datos para el periodo seleccionado.</td></tr>")
    return (f"<div style='background:{_CARD};border:1px solid {_BORDER};border-radius:10px;"
            "padding:10px 12px;'>"
            f"<div style='color:{_FG};font-size:13px;font-weight:700;margin-bottom:6px;'>{title}</div>"
            f"<table style='width:100%;border-collapse:collapse;'><thead><tr>{head}</tr></thead>"
            f"<tbody>{body}</tbody></table></div>")


def render_section_html(data: dict) -> str:
    """Renderiza una pestaña detallada (mini-KPIs + charts + tablas)."""
    kpis = "".join(_mini_kpi(k) for k in data.get("kpis", []))
    charts = "".join(_chart_card(c) for c in data.get("charts", []))
    tables = "".join(_table_card(t) for t in data.get("tables", []))
    return (
        "<html><head><meta charset='utf-8'>"
        f"<style>html,body{{margin:0;background:{_BG};color:{_FG};"
        "font-family:Inter,Arial,sans-serif;}svg{display:block;width:100%;height:100%;}"
        "*{box-sizing:border-box;}</style></head><body><div style='padding:12px;'>"
        f"<div style='display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px;'>{kpis}</div>"
        f"<div style='display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));"
        f"margin-bottom:12px;'>{charts}</div>"
        f"<div style='display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));'>"
        f"{tables}</div>"
        "</div></body></html>"
    )
