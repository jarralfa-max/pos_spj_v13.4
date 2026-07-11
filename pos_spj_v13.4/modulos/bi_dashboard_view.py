# -*- coding: utf-8 -*-
"""Renderer del dashboard ejecutivo BI a HTML autónomo (offline, theme-aware).

Transforma el `DashboardPayload` (dict) en HTML/SVG para un QWebEngineView.
Python puro y testeable (no importa PyQt). Colores desde design tokens globales
(`bi_theme`); superficie según el tema activo (claro/oscuro). KPI cards con icono,
estilo de tarjetas consistente y columna lateral de highlights/alertas/insights.
"""
from __future__ import annotations

from html import escape
from typing import Any

from modulos import bi_theme
from modulos.bi_charts import _bar_svg, _donut_svg, _hbar_svg, _line_svg

# Colores semánticos de estado (roles, independientes del tema).
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
    if value == int(value):
        return f"${int(value):,}"
    return f"${value:,.2f}"


def _delta_html(kpi: dict) -> str:
    semantic = kpi.get("semantic", "neutral")
    color = {"positive": _POS, "negative": _NEG}.get(semantic, _NEU)
    arrow = {"up": "▲", "down": "▼"}.get(kpi.get("direction", "flat"), "—")
    dp, pts = kpi.get("delta_pct"), kpi.get("delta_points")
    if dp is not None:
        txt = f"{abs(dp):.1f}% vs anterior"
    elif pts is not None:
        txt = f"{abs(pts):.2f} pp vs anterior"
    else:
        txt = "sin comparativo"
    return (f"<div style='color:{color};font-size:12px;margin-top:4px;'>"
            f"{arrow} {escape(txt)}</div>")


def _kpi_card(kpi: dict, pal: dict) -> str:
    title = escape(str(kpi.get("title", "")))
    tooltip = escape(str(kpi.get("formula", "") or kpi.get("tooltip", "")))
    icon = escape(str(kpi.get("icon", "") or ""))
    value = _fmt_value(kpi.get("value", 0), kpi.get("unit", ""))
    drill = str(kpi.get("drilldown", "") or "")
    cursor = "cursor:pointer;" if drill else ""
    hint = " · clic para detalle" if drill else ""
    icon_html = (f"<span style='font-size:18px;margin-right:6px;'>{icon}</span>" if icon else "")
    card = (
        f"<div title='{tooltip}{hint}' style='background:{pal['card']};"
        f"border:1px solid {pal['border']};border-radius:12px;padding:12px 14px;"
        f"min-width:160px;flex:1;{cursor}'>"
        f"<div style='color:{pal['muted']};font-size:11px;font-weight:700;"
        f"letter-spacing:.4px;text-transform:uppercase;'>{icon_html}{title}</div>"
        f"<div style='color:{pal['text']};font-size:24px;font-weight:700;margin-top:6px;'>{value}</div>"
        f"{_delta_html(kpi)}</div>"
    )
    if drill:
        return (f"<a href='spjdrill:{escape(drill)}' "
                "style='text-decoration:none;flex:1;display:flex;'>" + card + "</a>")
    return card


def _chart_svg_from_payload(chart: dict, pal: dict) -> str:
    kind = chart.get("kind", "bar")
    title = chart.get("title", "")
    labels = chart.get("labels", [])
    series = chart.get("series", [])
    prefix = "" if chart.get("unit") == "" else "$"
    if kind == "line":
        svg_series = [(s.get("name", ""), s.get("values", []),
                       s.get("color", "primary")) for s in series]
        return _line_svg(title, labels, svg_series, pal, prefix)
    values = series[0].get("values", []) if series else []
    color = _c(series[0].get("color", "primary")) if series else _c("primary")
    if kind == "hbar":
        return _hbar_svg(title, labels, values, pal, prefix, color)
    if kind == "donut":
        return _donut_svg(title, labels, values, pal, prefix)
    return _bar_svg(title, labels, values, pal, prefix, color)


def _chart_card(chart: dict, pal: dict) -> str:
    return (f"<div style='background:{pal['card']};border:1px solid {pal['border']};"
            "border-radius:12px;padding:8px;'>" + _chart_svg_from_payload(chart, pal) + "</div>")


def _drill_wrap(html: str, drill: str) -> str:
    drill = str(drill or "")
    if not drill:
        return html
    return (f"<a href='spjdrill:{escape(drill)}' "
            "style='text-decoration:none;display:block;cursor:pointer;'>" + html + "</a>")


def _highlight_card(h: dict, pal: dict) -> str:
    title = escape(str(h.get("title", "")))
    name = escape(str(h.get("name", "")))
    value = _fmt_value(h.get("value", 0), h.get("unit", "$"))
    share = h.get("share_pct", 0)
    card = (
        f"<div style='background:{pal['card']};border:1px solid {pal['border']};border-radius:12px;"
        "padding:10px 12px;margin-bottom:8px;'>"
        f"<div style='color:{_GOLD};font-size:11px;font-weight:700;text-transform:uppercase;'>{title}</div>"
        f"<div style='color:{pal['text']};font-size:16px;font-weight:700;margin-top:2px;'>{name}</div>"
        f"<div style='color:{pal['muted']};font-size:13px;'>{value} · {share:.1f}% del total</div></div>"
    )
    return _drill_wrap(card, h.get("drilldown", ""))


def _alert_item(a: dict, pal: dict) -> str:
    color = {"critical": _NEG, "warning": _GOLD}.get(a.get("level"), pal["muted"])
    title = escape(str(a.get("title", "")))
    detail = escape(str(a.get("detail", "")))
    return (f"<div style='border-left:3px solid {color};padding:6px 10px;margin-bottom:6px;'>"
            f"<div style='color:{pal['text']};font-size:13px;font-weight:700;'>⚠ {title}</div>"
            f"<div style='color:{pal['muted']};font-size:12px;'>{detail}</div></div>")


def _insight_item(i: dict, pal: dict) -> str:
    title = escape(str(i.get("title", "")))
    detail = escape(str(i.get("detail", "")))
    item = (f"<div style='padding:5px 0;border-bottom:1px solid {pal['border']};'>"
            f"<div style='color:{pal['text']};font-size:13px;'>• {title}</div>"
            f"<div style='color:{pal['muted']};font-size:12px;margin-left:10px;'>{detail}</div></div>")
    return _drill_wrap(item, i.get("drilldown", ""))


def _prediction_card(pred: dict, pal: dict) -> str:
    if not pred:
        return ""
    title = escape(str(pred.get("title", "")))
    value = _fmt_value(pred.get("value", 0), pred.get("unit", "$"))
    detail = escape(str(pred.get("detail", "")))
    return (
        f"<div style='background:{pal['card']};border:1px solid {pal['border']};border-radius:12px;"
        "padding:10px 12px;margin-bottom:8px;'>"
        f"<div style='color:{_POS};font-size:11px;font-weight:700;text-transform:uppercase;'>{title}</div>"
        f"<div style='color:{pal['text']};font-size:19px;font-weight:700;'>{value}</div>"
        f"<div style='color:{pal['muted']};font-size:12px;'>{detail}</div></div>"
    )


def _page(pal: dict, body: str) -> str:
    return (
        "<html><head><meta charset='utf-8'>"
        f"<style>html,body{{margin:0;background:{pal['bg']};color:{pal['text']};"
        "font-family:'Segoe UI',Inter,Arial,sans-serif;}svg{display:block;width:100%;height:100%;}"
        "*{box-sizing:border-box;}</style></head><body>" + body + "</body></html>"
    )


_CHART_ORDER = ("sales_trend", "branch_sales", "top_products", "categories",
                "payment_methods", "peak_hours", "forecast", "profitability")


def render_dashboard_html(payload: dict, theme: str = "dark",
                          include_kpis: bool = True) -> str:
    """Dashboard ejecutivo completo desde el payload, según el tema activo.

    include_kpis=False omite la fila de KPIs (la UI los muestra como KPICard
    nativas, igual que el módulo de Inventario).
    """
    pal = bi_theme.surface(theme)
    kpis = payload.get("kpis", [])
    charts = payload.get("charts", {})
    highlights = payload.get("highlights", {})
    alerts = payload.get("alerts", [])
    insights = payload.get("insights", [])
    predictions = payload.get("predictions", {})

    kpi_row = "".join(_kpi_card(k, pal) for k in kpis) if include_kpis else ""
    chart_cards = "".join(_chart_card(charts[k], pal) for k in _CHART_ORDER if k in charts)

    side = []
    for key in ("top_product", "top_category", "top_branch"):
        if key in highlights:
            side.append(_highlight_card(highlights[key], pal))
    if predictions.get("next_week"):
        side.append(_prediction_card(predictions["next_week"], pal))
    if alerts:
        side.append(f"<div style='color:{_GOLD};font-size:12px;font-weight:700;"
                    "text-transform:uppercase;margin:6px 0 4px;'>Alertas BI</div>")
        side.extend(_alert_item(a, pal) for a in alerts)
    if insights:
        side.append(f"<div style='color:{pal['muted']};font-size:12px;font-weight:700;"
                    "text-transform:uppercase;margin:8px 0 4px;'>Insights clave</div>")
        side.extend(_insight_item(i, pal) for i in insights)
    sidebar = "".join(side)

    kpi_block = (f"<div style='display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px;'>{kpi_row}</div>"
                 if kpi_row else "")
    body = (
        "<div style='padding:12px;'>"
        f"{kpi_block}"
        "<div style='display:grid;grid-template-columns:minmax(0,3fr) minmax(220px,1fr);gap:12px;'>"
        "<div style='display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));'>"
        f"{chart_cards}</div>"
        f"<div>{sidebar}</div>"
        "</div></div>"
    )
    return _page(pal, body)


# ── Vistas de secciones detalladas ────────────────────────────────────────────

def _mini_kpi(k: dict, pal: dict) -> str:
    title = escape(str(k.get("title", "")))
    icon = escape(str(k.get("icon", "") or ""))
    value = _fmt_value(k.get("value", 0), k.get("unit", "$"))
    icon_html = (f"<span style='font-size:16px;margin-right:5px;'>{icon}</span>" if icon else "")
    return (f"<div style='background:{pal['card']};border:1px solid {pal['border']};border-radius:12px;"
            "padding:10px 14px;min-width:140px;flex:1;'>"
            f"<div style='color:{pal['muted']};font-size:11px;font-weight:700;"
            f"text-transform:uppercase;'>{icon_html}{title}</div>"
            f"<div style='color:{pal['text']};font-size:22px;font-weight:700;margin-top:4px;'>{value}</div></div>")


def _table_card(tbl: dict, pal: dict) -> str:
    title = escape(str(tbl.get("title", "")))
    cols = tbl.get("columns", [])
    rows = tbl.get("rows", [])
    head = "".join(f"<th style='text-align:left;padding:6px 8px;color:{pal['muted']};"
                   f"border-bottom:1px solid {pal['border']};font-size:12px;'>{escape(str(c))}</th>"
                   for c in cols)
    if rows:
        body = ""
        for r in rows:
            tds = "".join(f"<td style='padding:5px 8px;color:{pal['text']};font-size:13px;"
                          f"border-bottom:1px solid {pal['border']};'>{escape(str(v))}</td>" for v in r)
            body += f"<tr>{tds}</tr>"
    else:
        body = (f"<tr><td colspan='{max(1,len(cols))}' style='padding:10px;color:{pal['muted']};"
                "font-size:13px;'>Sin datos para el periodo seleccionado.</td></tr>")
    return (f"<div style='background:{pal['card']};border:1px solid {pal['border']};border-radius:12px;"
            "padding:10px 12px;'>"
            f"<div style='color:{pal['text']};font-size:14px;font-weight:700;margin-bottom:6px;'>{title}</div>"
            f"<table style='width:100%;border-collapse:collapse;'><thead><tr>{head}</tr></thead>"
            f"<tbody>{body}</tbody></table></div>")


def render_section_html(data: dict, theme: str = "dark") -> str:
    """Pestaña detallada (mini-KPIs + charts + tablas), según el tema activo."""
    pal = bi_theme.surface(theme)
    kpis = "".join(_mini_kpi(k, pal) for k in data.get("kpis", []))
    charts = "".join(_chart_card(c, pal) for c in data.get("charts", []))
    tables = "".join(_table_card(t, pal) for t in data.get("tables", []))
    body = (
        "<div style='padding:12px;'>"
        f"<div style='display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px;'>{kpis}</div>"
        f"<div style='display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));"
        f"margin-bottom:12px;'>{charts}</div>"
        f"<div style='display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));'>"
        f"{tables}</div></div>"
    )
    return _page(pal, body)
