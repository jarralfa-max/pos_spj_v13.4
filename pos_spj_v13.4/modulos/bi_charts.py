# -*- coding: utf-8 -*-
"""bi_charts — generación de gráficas BI como SVG embebido (offline).

El dashboard usaba ECharts vía CDN (https://cdn.jsdelivr.net/...), que no carga
sin internet y dejaba las gráficas en blanco. Este módulo genera HTML autónomo
con SVG inline — sin red, sin JS, sin dependencias — para mostrar en un
QWebEngineView (o cualquier vista HTML). Es Python puro y testeable.
"""
from __future__ import annotations

from html import escape
from typing import Sequence

# Paleta oscura consistente con el dashboard.
_BG = "#0b1220"
_FG = "#e2e8f0"
_MUTED = "#94a3b8"
_GRID = "#1f2937"
_BAR = "#3b82f6"
_LINE = "#22c55e"


def _fmt(v: float, prefix: str) -> str:
    try:
        return f"{prefix}{float(v):,.0f}"
    except Exception:
        return f"{prefix}0"


def _page(title: str, body_svg: str) -> str:
    return (
        "<html><head><meta charset='utf-8'>"
        f"<style>html,body{{height:100%;margin:0;background:{_BG};"
        f"color:{_FG};font-family:Inter,Arial,sans-serif;}}"
        "svg{width:100%;height:100%;display:block;}</style></head>"
        f"<body>{body_svg}</body></html>"
    )


def _empty(title: str) -> str:
    svg = (
        "<svg viewBox='0 0 400 200' preserveAspectRatio='xMidYMid meet'>"
        f"<text x='200' y='96' fill='{_FG}' font-size='16' font-weight='700' "
        f"text-anchor='middle'>{escape(title)}</text>"
        f"<text x='200' y='120' fill='{_MUTED}' font-size='12' "
        "text-anchor='middle'>Sin datos para graficar</text></svg>"
    )
    return _page(title, svg)


def bar_chart_html(
    title: str,
    labels: Sequence[str],
    values: Sequence[float],
    unit_prefix: str = "$",
) -> str:
    """Gráfica de barras vertical como SVG embebido."""
    pares = [(str(l), float(v or 0)) for l, v in zip(labels, values)]
    pares = [(l, v) for l, v in pares if v != 0] or pares
    if not pares:
        return _empty(title)

    W, H = 760, 380
    pad_l, pad_r, pad_t, pad_b = 40, 20, 50, 90
    plot_w = W - pad_l - pad_r
    plot_h = H - pad_t - pad_b
    vmax = max(v for _, v in pares) or 1.0
    n = len(pares)
    slot = plot_w / n
    bw = min(48.0, slot * 0.6)

    parts = [
        f"<svg viewBox='0 0 {W} {H}' preserveAspectRatio='xMidYMid meet'>",
        f"<text x='{W/2:.0f}' y='26' fill='{_FG}' font-size='16' "
        f"font-weight='700' text-anchor='middle'>{escape(title)}</text>",
        f"<line x1='{pad_l}' y1='{pad_t+plot_h}' x2='{W-pad_r}' "
        f"y2='{pad_t+plot_h}' stroke='{_GRID}' stroke-width='1'/>",
    ]
    for i, (lbl, val) in enumerate(pares):
        h = (val / vmax) * plot_h
        x = pad_l + slot * i + (slot - bw) / 2
        y = pad_t + plot_h - h
        cx = x + bw / 2
        parts.append(
            f"<rect x='{x:.1f}' y='{y:.1f}' width='{bw:.1f}' height='{h:.1f}' "
            f"rx='3' fill='{_BAR}'/>"
        )
        parts.append(
            f"<text x='{cx:.1f}' y='{y-6:.1f}' fill='{_FG}' font-size='10' "
            f"text-anchor='middle'>{_fmt(val, unit_prefix)}</text>"
        )
        etq = lbl if len(lbl) <= 14 else lbl[:13] + "…"
        parts.append(
            f"<text x='{cx:.1f}' y='{pad_t+plot_h+14:.1f}' fill='{_MUTED}' "
            f"font-size='10' text-anchor='end' "
            f"transform='rotate(-35 {cx:.1f} {pad_t+plot_h+14:.1f})'>"
            f"{escape(etq)}</text>"
        )
    parts.append("</svg>")
    return _page(title, "".join(parts))


def line_chart_html(
    title: str,
    labels: Sequence[str],
    values: Sequence[float],
    unit_prefix: str = "$",
) -> str:
    """Gráfica de línea como SVG embebido (p. ej. proyección de forecast)."""
    pares = [(str(l), float(v or 0)) for l, v in zip(labels, values)]
    if not pares:
        return _empty(title)

    W, H = 760, 380
    pad_l, pad_r, pad_t, pad_b = 50, 20, 50, 70
    plot_w = W - pad_l - pad_r
    plot_h = H - pad_t - pad_b
    vmax = max(v for _, v in pares) or 1.0
    n = len(pares)
    step = plot_w / max(1, n - 1)

    pts = []
    for i, (_, val) in enumerate(pares):
        x = pad_l + step * i
        y = pad_t + plot_h - (val / vmax) * plot_h
        pts.append((x, y))

    parts = [
        f"<svg viewBox='0 0 {W} {H}' preserveAspectRatio='xMidYMid meet'>",
        f"<text x='{W/2:.0f}' y='26' fill='{_FG}' font-size='16' "
        f"font-weight='700' text-anchor='middle'>{escape(title)}</text>",
        f"<line x1='{pad_l}' y1='{pad_t+plot_h}' x2='{W-pad_r}' "
        f"y2='{pad_t+plot_h}' stroke='{_GRID}' stroke-width='1'/>",
    ]
    poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    parts.append(
        f"<polyline points='{poly}' fill='none' stroke='{_LINE}' "
        "stroke-width='2'/>"
    )
    for (x, y), (lbl, val) in zip(pts, pares):
        parts.append(f"<circle cx='{x:.1f}' cy='{y:.1f}' r='3' fill='{_LINE}'/>")
        parts.append(
            f"<text x='{x:.1f}' y='{y-8:.1f}' fill='{_FG}' font-size='9' "
            f"text-anchor='middle'>{_fmt(val, unit_prefix)}</text>"
        )
        etq = lbl if len(lbl) <= 10 else lbl[5:]  # fechas: recorta año
        parts.append(
            f"<text x='{x:.1f}' y='{pad_t+plot_h+16:.1f}' fill='{_MUTED}' "
            f"font-size='9' text-anchor='middle'>{escape(etq)}</text>"
        )
    parts.append("</svg>")
    return _page(title, "".join(parts))
