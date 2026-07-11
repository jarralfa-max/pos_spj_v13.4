# -*- coding: utf-8 -*-
"""bi_charts — gráficas BI como SVG embebido (offline, sin CDN).

El dashboard usaba ECharts vía CDN, que no carga sin internet y dejaba las
gráficas en blanco. Este módulo genera HTML/SVG autónomo — sin red, sin JS, sin
dependencias — para mostrar en un QWebEngineView. Es Python puro y testeable.

Paleta consistente con el módulo BI (tarjetas #1E293B sobre fondo #0b1220):
azul para la serie principal y ámbar para la secundaria (utilidad/margen), en
línea con el dashboard ejecutivo de referencia.
"""
from __future__ import annotations

import math
from html import escape
from typing import Sequence

_BG = "#0b1220"
_CARD = "#111a2e"
_FG = "#e2e8f0"
_MUTED = "#94a3b8"
_GRID = "#1f2937"
_BLUE = "#3b82f6"
_GOLD = "#eab308"
_GREEN = "#22c55e"
# Paleta categórica para donas / series múltiples.
_PALETTE = ["#3b82f6", "#eab308", "#22c55e", "#a855f7", "#ef4444",
            "#14b8a6", "#f97316", "#64748b"]


def _fmt(v: float, prefix: str) -> str:
    try:
        return f"{prefix}{float(v):,.0f}"
    except Exception:
        return f"{prefix}0"


def _page(body: str) -> str:
    return (
        "<html><head><meta charset='utf-8'>"
        f"<style>html,body{{margin:0;background:{_BG};color:{_FG};"
        "font-family:Inter,Arial,sans-serif;}svg{display:block;width:100%;height:100%;}"
        "</style></head><body>" + body + "</body></html>"
    )


def _empty_svg(title: str) -> str:
    return (
        "<svg viewBox='0 0 400 200' preserveAspectRatio='xMidYMid meet'>"
        f"<text x='200' y='96' fill='{_FG}' font-size='15' font-weight='700' "
        f"text-anchor='middle'>{escape(title)}</text>"
        f"<text x='200' y='118' fill='{_MUTED}' font-size='12' "
        "text-anchor='middle'>Sin datos para graficar</text></svg>"
    )


# ── Fragmentos SVG (sin wrapper de página) ────────────────────────────────────

def _bar_svg(title, labels, values, prefix="$", color=_BLUE) -> str:
    pares = [(str(l), float(v or 0)) for l, v in zip(labels, values)]
    if not pares or all(v == 0 for _, v in pares):
        return _empty_svg(title)
    W, H = 760, 380
    pl, pr, pt, pb = 44, 20, 50, 92
    pw, ph = W - pl - pr, H - pt - pb
    vmax = max(v for _, v in pares) or 1.0
    n = len(pares)
    slot = pw / n
    bw = min(48.0, slot * 0.6)
    p = [f"<svg viewBox='0 0 {W} {H}' preserveAspectRatio='xMidYMid meet'>",
         f"<text x='{W/2:.0f}' y='26' fill='{_FG}' font-size='15' font-weight='700' "
         f"text-anchor='middle'>{escape(title)}</text>",
         f"<line x1='{pl}' y1='{pt+ph}' x2='{W-pr}' y2='{pt+ph}' stroke='{_GRID}'/>"]
    for i, (lbl, val) in enumerate(pares):
        h = (val / vmax) * ph
        x = pl + slot * i + (slot - bw) / 2
        y = pt + ph - h
        cx = x + bw / 2
        p.append(f"<rect x='{x:.1f}' y='{y:.1f}' width='{bw:.1f}' height='{h:.1f}' "
                 f"rx='3' fill='{color}'/>")
        p.append(f"<text x='{cx:.1f}' y='{y-6:.1f}' fill='{_FG}' font-size='10' "
                 f"text-anchor='middle'>{_fmt(val, prefix)}</text>")
        etq = lbl if len(lbl) <= 14 else lbl[:13] + "…"
        p.append(f"<text x='{cx:.1f}' y='{pt+ph+14:.1f}' fill='{_MUTED}' font-size='10' "
                 f"text-anchor='end' transform='rotate(-35 {cx:.1f} {pt+ph+14:.1f})'>"
                 f"{escape(etq)}</text>")
    p.append("</svg>")
    return "".join(p)


def _hbar_svg(title, labels, values, prefix="$", color=_BLUE) -> str:
    pares = [(str(l), float(v or 0)) for l, v in zip(labels, values)]
    if not pares or all(v == 0 for _, v in pares):
        return _empty_svg(title)
    row_h = 30
    W = 760
    pt, pb, pl, pr = 48, 20, 170, 70
    H = pt + pb + row_h * len(pares)
    pw = W - pl - pr
    vmax = max(v for _, v in pares) or 1.0
    p = [f"<svg viewBox='0 0 {W} {H}' preserveAspectRatio='xMidYMid meet'>",
         f"<text x='{W/2:.0f}' y='26' fill='{_FG}' font-size='15' font-weight='700' "
         f"text-anchor='middle'>{escape(title)}</text>"]
    for i, (lbl, val) in enumerate(pares):
        y = pt + i * row_h
        bw = (val / vmax) * pw
        etq = lbl if len(lbl) <= 22 else lbl[:21] + "…"
        p.append(f"<text x='{pl-8}' y='{y+row_h*0.62:.1f}' fill='{_MUTED}' font-size='11' "
                 f"text-anchor='end'>{escape(etq)}</text>")
        p.append(f"<rect x='{pl}' y='{y+5:.1f}' width='{max(bw,1):.1f}' height='{row_h-12}' "
                 f"rx='3' fill='{color}'/>")
        p.append(f"<text x='{pl+bw+6:.1f}' y='{y+row_h*0.62:.1f}' fill='{_FG}' "
                 f"font-size='10'>{_fmt(val, prefix)}</text>")
    p.append("</svg>")
    return "".join(p)


def _line_svg(title, labels, series, prefix="$") -> str:
    """series: lista de (nombre, valores, color)."""
    series = [(nm, [float(v or 0) for v in vals], col) for nm, vals, col in series]
    if not series or not any(any(vals) for _, vals, _ in series):
        return _empty_svg(title)
    W, H = 760, 380
    pl, pr, pt, pb = 52, 20, 54, 60
    pw, ph = W - pl - pr, H - pt - pb
    n = max(len(v) for _, v, _ in series)
    _maxes = [max(vals) for _, vals, _ in series if vals]
    vmax = (max(_maxes) if _maxes else 1.0) or 1.0
    step = pw / max(1, n - 1)
    p = [f"<svg viewBox='0 0 {W} {H}' preserveAspectRatio='xMidYMid meet'>",
         f"<text x='{W/2:.0f}' y='26' fill='{_FG}' font-size='15' font-weight='700' "
         f"text-anchor='middle'>{escape(title)}</text>",
         f"<line x1='{pl}' y1='{pt+ph}' x2='{W-pr}' y2='{pt+ph}' stroke='{_GRID}'/>"]
    for nm, vals, col in series:
        pts = [(pl + step * i, pt + ph - (v / vmax) * ph) for i, v in enumerate(vals)]
        poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        p.append(f"<polyline points='{poly}' fill='none' stroke='{col}' stroke-width='2'/>")
        for x, y in pts:
            p.append(f"<circle cx='{x:.1f}' cy='{y:.1f}' r='2.5' fill='{col}'/>")
    # etiquetas eje X
    for i, lbl in enumerate(labels[:n]):
        x = pl + step * i
        etq = escape(str(lbl))
        p.append(f"<text x='{x:.1f}' y='{pt+ph+16:.1f}' fill='{_MUTED}' font-size='9' "
                 f"text-anchor='middle'>{etq}</text>")
    # leyenda
    lx = pl
    for nm, _, col in series:
        p.append(f"<rect x='{lx}' y='34' width='10' height='10' fill='{col}'/>")
        p.append(f"<text x='{lx+14}' y='43' fill='{_MUTED}' font-size='10'>{escape(nm)}</text>")
        lx += 14 + 8 * len(nm) + 18
    p.append("</svg>")
    return "".join(p)


def _donut_svg(title, labels, values, prefix="$") -> str:
    pares = [(str(l), float(v or 0)) for l, v in zip(labels, values) if float(v or 0) > 0]
    if not pares:
        return _empty_svg(title)
    total = sum(v for _, v in pares) or 1.0
    W, H = 760, 380
    cx, cy, r, rin = 250, 210, 130, 72
    p = [f"<svg viewBox='0 0 {W} {H}' preserveAspectRatio='xMidYMid meet'>",
         f"<text x='{W/2:.0f}' y='26' fill='{_FG}' font-size='15' font-weight='700' "
         f"text-anchor='middle'>{escape(title)}</text>"]
    ang = -math.pi / 2
    for i, (lbl, val) in enumerate(pares):
        frac = val / total
        a2 = ang + frac * 2 * math.pi
        large = 1 if frac > 0.5 else 0
        x1, y1 = cx + r * math.cos(ang), cy + r * math.sin(ang)
        x2, y2 = cx + r * math.cos(a2), cy + r * math.sin(a2)
        col = _PALETTE[i % len(_PALETTE)]
        p.append(f"<path d='M {x1:.1f} {y1:.1f} A {r} {r} 0 {large} 1 {x2:.1f} {y2:.1f} "
                 f"L {cx} {cy} Z' fill='{col}'/>")
        ang = a2
    p.append(f"<circle cx='{cx}' cy='{cy}' r='{rin}' fill='{_BG}'/>")
    # leyenda a la derecha
    ly = 90
    for i, (lbl, val) in enumerate(pares):
        col = _PALETTE[i % len(_PALETTE)]
        pct = val / total * 100
        p.append(f"<rect x='430' y='{ly}' width='12' height='12' rx='2' fill='{col}'/>")
        etq = lbl if len(lbl) <= 18 else lbl[:17] + "…"
        p.append(f"<text x='448' y='{ly+11}' fill='{_FG}' font-size='11'>"
                 f"{escape(etq)}  {_fmt(val, prefix)} ({pct:.0f}%)</text>")
        ly += 26
    p.append("</svg>")
    return "".join(p)


# ── API pública: gráficas individuales (una por página) ───────────────────────

def bar_chart_html(title, labels, values, unit_prefix="$") -> str:
    return _page(_bar_svg(title, labels, values, unit_prefix))


def line_chart_html(title, labels, values, unit_prefix="$") -> str:
    return _page(_line_svg(title, labels, [("", values, _GREEN)], unit_prefix))


def hbar_chart_html(title, labels, values, unit_prefix="$") -> str:
    return _page(_hbar_svg(title, labels, values, unit_prefix))


def donut_chart_html(title, labels, values, unit_prefix="$") -> str:
    return _page(_donut_svg(title, labels, values, unit_prefix))


# ── API pública: dashboard compuesto (varias gráficas en una página) ──────────

def dashboard_html(panels: Sequence[dict]) -> str:
    """Compone un dashboard con múltiples paneles SVG en una grilla responsiva.

    panels: lista de dicts con {kind, title, ...}:
      kind='bar'/'hbar'  → title, labels, values, [prefix], [color]
      kind='line'        → title, labels, series=[(nombre, valores, color)], [prefix]
      kind='donut'       → title, labels, values, [prefix]
    """
    cards = []
    for pn in panels:
        kind = pn.get("kind", "bar")
        prefix = pn.get("prefix", "$")
        if kind == "hbar":
            svg = _hbar_svg(pn["title"], pn["labels"], pn["values"], prefix,
                            pn.get("color", _BLUE))
        elif kind == "line":
            svg = _line_svg(pn["title"], pn["labels"], pn["series"], prefix)
        elif kind == "donut":
            svg = _donut_svg(pn["title"], pn["labels"], pn["values"], prefix)
        else:
            svg = _bar_svg(pn["title"], pn["labels"], pn["values"], prefix,
                           pn.get("color", _BLUE))
        cards.append(
            f"<div style='background:{_CARD};border:1px solid {_GRID};"
            "border-radius:10px;padding:8px;'>" + svg + "</div>")
    grid = (
        "<div style='display:grid;gap:12px;padding:12px;"
        "grid-template-columns:repeat(auto-fit,minmax(340px,1fr));'>"
        + "".join(cards) + "</div>"
    )
    return _page(grid)
