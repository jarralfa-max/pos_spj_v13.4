# -*- coding: utf-8 -*-
"""bi_charts — gráficas BI como SVG embebido (offline, sin CDN, theme-aware).

Genera HTML/SVG autónomo — sin red, sin JS, sin dependencias — para mostrar en un
QWebEngineView. Python puro y testeable. Todos los colores provienen de los design
tokens globales (via `bi_theme`): los roles de serie (primary/secondary/…) y la
superficie (bg/card/text/muted/grid) según el tema activo (claro/oscuro).
"""
from __future__ import annotations

import math
from html import escape
from typing import Sequence

from modulos import bi_theme

_BLUE = bi_theme.ROLE["primary"]
_GOLD = bi_theme.ROLE["secondary"]
_GREEN = bi_theme.ROLE["positive"]
_PALETTE = bi_theme.PALETTE
_c = bi_theme.color  # resuelve rol/hex → color


def _fmt(v: float, prefix: str) -> str:
    try:
        return f"{prefix}{float(v):,.0f}"
    except Exception:
        return f"{prefix}0"


def _page(pal: dict, body: str) -> str:
    return (
        "<html><head><meta charset='utf-8'>"
        f"<style>html,body{{margin:0;background:{pal['bg']};color:{pal['text']};"
        "font-family:'Segoe UI',Inter,Arial,sans-serif;}"
        "svg{display:block;width:100%;height:100%;}</style></head><body>" + body + "</body></html>"
    )


def _empty_svg(title: str, pal: dict) -> str:
    return (
        "<svg viewBox='0 0 400 200' preserveAspectRatio='xMidYMid meet'>"
        f"<text x='200' y='96' fill='{pal['text']}' font-size='17' font-weight='700' "
        f"text-anchor='middle'>{escape(title)}</text>"
        f"<text x='200' y='120' fill='{pal['muted']}' font-size='13' "
        "text-anchor='middle'>Sin datos para graficar</text></svg>"
    )


# ── Fragmentos SVG (reciben la paleta de superficie `pal`) ────────────────────

def _bar_svg(title, labels, values, pal, prefix="$", color=_BLUE) -> str:
    color = _c(color)
    pares = [(str(l), float(v or 0)) for l, v in zip(labels, values)]
    if not pares or all(v == 0 for _, v in pares):
        return _empty_svg(title, pal)
    W, H = 760, 400
    pl, pr, pt, pb = 46, 20, 54, 104
    pw, ph = W - pl - pr, H - pt - pb
    vmax = max(v for _, v in pares) or 1.0
    n = len(pares)
    slot = pw / n
    bw = min(52.0, slot * 0.6)
    p = [f"<svg viewBox='0 0 {W} {H}' preserveAspectRatio='xMidYMid meet'>",
         f"<text x='{W/2:.0f}' y='28' fill='{pal['text']}' font-size='18' font-weight='700' "
         f"text-anchor='middle'>{escape(title)}</text>",
         f"<line x1='{pl}' y1='{pt+ph}' x2='{W-pr}' y2='{pt+ph}' stroke='{pal['grid']}'/>"]
    for i, (lbl, val) in enumerate(pares):
        h = (val / vmax) * ph
        x = pl + slot * i + (slot - bw) / 2
        y = pt + ph - h
        cx = x + bw / 2
        p.append(f"<rect x='{x:.1f}' y='{y:.1f}' width='{bw:.1f}' height='{h:.1f}' "
                 f"rx='3' fill='{color}'/>")
        p.append(f"<text x='{cx:.1f}' y='{y-7:.1f}' fill='{pal['text']}' font-size='13' "
                 f"text-anchor='middle'>{_fmt(val, prefix)}</text>")
        etq = lbl if len(lbl) <= 16 else lbl[:15] + "…"
        p.append(f"<text x='{cx:.1f}' y='{pt+ph+16:.1f}' fill='{pal['muted']}' font-size='13' "
                 f"text-anchor='end' transform='rotate(-32 {cx:.1f} {pt+ph+16:.1f})'>"
                 f"{escape(etq)}</text>")
    p.append("</svg>")
    return "".join(p)


def _hbar_svg(title, labels, values, pal, prefix="$", color=_BLUE) -> str:
    color = _c(color)
    pares = [(str(l), float(v or 0)) for l, v in zip(labels, values)]
    if not pares or all(v == 0 for _, v in pares):
        return _empty_svg(title, pal)
    row_h = 34
    W = 760
    pt, pb, pl, pr = 52, 20, 190, 80
    H = pt + pb + row_h * len(pares)
    pw = W - pl - pr
    vmax = max(v for _, v in pares) or 1.0
    p = [f"<svg viewBox='0 0 {W} {H}' preserveAspectRatio='xMidYMid meet'>",
         f"<text x='{W/2:.0f}' y='28' fill='{pal['text']}' font-size='18' font-weight='700' "
         f"text-anchor='middle'>{escape(title)}</text>"]
    for i, (lbl, val) in enumerate(pares):
        y = pt + i * row_h
        bw = (val / vmax) * pw
        etq = lbl if len(lbl) <= 24 else lbl[:23] + "…"
        p.append(f"<text x='{pl-8}' y='{y+row_h*0.62:.1f}' fill='{pal['muted']}' font-size='13' "
                 f"text-anchor='end'>{escape(etq)}</text>")
        p.append(f"<rect x='{pl}' y='{y+6:.1f}' width='{max(bw,1):.1f}' height='{row_h-13}' "
                 f"rx='3' fill='{color}'/>")
        p.append(f"<text x='{pl+bw+7:.1f}' y='{y+row_h*0.62:.1f}' fill='{pal['text']}' "
                 f"font-size='12'>{_fmt(val, prefix)}</text>")
    p.append("</svg>")
    return "".join(p)


def _line_svg(title, labels, series, pal, prefix="$") -> str:
    """series: lista de (nombre, valores, color|rol)."""
    series = [(nm, [float(v or 0) for v in vals], _c(col)) for nm, vals, col in series]
    if not series or not any(any(vals) for _, vals, _ in series):
        return _empty_svg(title, pal)
    W, H = 760, 400
    pl, pr, pt, pb = 54, 20, 58, 62
    pw, ph = W - pl - pr, H - pt - pb
    n = max(len(v) for _, v, _ in series)
    _maxes = [max(vals) for _, vals, _ in series if vals]
    vmax = (max(_maxes) if _maxes else 1.0) or 1.0
    step = pw / max(1, n - 1)
    p = [f"<svg viewBox='0 0 {W} {H}' preserveAspectRatio='xMidYMid meet'>",
         f"<text x='{W/2:.0f}' y='28' fill='{pal['text']}' font-size='18' font-weight='700' "
         f"text-anchor='middle'>{escape(title)}</text>",
         f"<line x1='{pl}' y1='{pt+ph}' x2='{W-pr}' y2='{pt+ph}' stroke='{pal['grid']}'/>"]
    for nm, vals, col in series:
        pts = [(pl + step * i, pt + ph - (v / vmax) * ph) for i, v in enumerate(vals)]
        poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        p.append(f"<polyline points='{poly}' fill='none' stroke='{col}' stroke-width='2.5'/>")
        for x, y in pts:
            p.append(f"<circle cx='{x:.1f}' cy='{y:.1f}' r='3' fill='{col}'/>")
    for i, lbl in enumerate(labels[:n]):
        x = pl + step * i
        p.append(f"<text x='{x:.1f}' y='{pt+ph+18:.1f}' fill='{pal['muted']}' font-size='12' "
                 f"text-anchor='middle'>{escape(str(lbl))}</text>")
    lx = pl
    for nm, _, col in series:
        p.append(f"<rect x='{lx}' y='36' width='12' height='12' rx='2' fill='{col}'/>")
        p.append(f"<text x='{lx+16}' y='46' fill='{pal['muted']}' font-size='12'>{escape(nm)}</text>")
        lx += 16 + 9 * len(nm) + 22
    p.append("</svg>")
    return "".join(p)


def _donut_svg(title, labels, values, pal, prefix="$") -> str:
    pares = [(str(l), float(v or 0)) for l, v in zip(labels, values) if float(v or 0) > 0]
    if not pares:
        return _empty_svg(title, pal)
    total = sum(v for _, v in pares) or 1.0
    W, H = 760, 400
    cx, cy, r, rin = 230, 220, 140, 78
    p = [f"<svg viewBox='0 0 {W} {H}' preserveAspectRatio='xMidYMid meet'>",
         f"<text x='{W/2:.0f}' y='28' fill='{pal['text']}' font-size='18' font-weight='700' "
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
    p.append(f"<circle cx='{cx}' cy='{cy}' r='{rin}' fill='{pal['bg']}'/>")
    ly = 96
    for i, (lbl, val) in enumerate(pares):
        col = _PALETTE[i % len(_PALETTE)]
        pct = val / total * 100
        p.append(f"<rect x='430' y='{ly}' width='14' height='14' rx='2' fill='{col}'/>")
        etq = lbl if len(lbl) <= 18 else lbl[:17] + "…"
        p.append(f"<text x='450' y='{ly+12}' fill='{pal['text']}' font-size='13'>"
                 f"{escape(etq)}  {_fmt(val, prefix)} ({pct:.0f}%)</text>")
        ly += 30
    p.append("</svg>")
    return "".join(p)


# ── API pública: gráficas individuales (una por página) ───────────────────────

def bar_chart_html(title, labels, values, unit_prefix="$", theme="dark") -> str:
    pal = bi_theme.surface(theme)
    return _page(pal, _bar_svg(title, labels, values, pal, unit_prefix))


def line_chart_html(title, labels, values, unit_prefix="$", theme="dark") -> str:
    pal = bi_theme.surface(theme)
    return _page(pal, _line_svg(title, labels, [("", values, _GREEN)], pal, unit_prefix))


def hbar_chart_html(title, labels, values, unit_prefix="$", theme="dark") -> str:
    pal = bi_theme.surface(theme)
    return _page(pal, _hbar_svg(title, labels, values, pal, unit_prefix))


def donut_chart_html(title, labels, values, unit_prefix="$", theme="dark") -> str:
    pal = bi_theme.surface(theme)
    return _page(pal, _donut_svg(title, labels, values, pal, unit_prefix))


# ── API pública: dashboard compuesto ──────────────────────────────────────────

def dashboard_html(panels: Sequence[dict], theme="dark") -> str:
    pal = bi_theme.surface(theme)
    cards = []
    for pn in panels:
        kind = pn.get("kind", "bar")
        prefix = pn.get("prefix", "$")
        if kind == "hbar":
            svg = _hbar_svg(pn["title"], pn["labels"], pn["values"], pal, prefix,
                            pn.get("color", _BLUE))
        elif kind == "line":
            svg = _line_svg(pn["title"], pn["labels"], pn["series"], pal, prefix)
        elif kind == "donut":
            svg = _donut_svg(pn["title"], pn["labels"], pn["values"], pal, prefix)
        else:
            svg = _bar_svg(pn["title"], pn["labels"], pn["values"], pal, prefix,
                           pn.get("color", _BLUE))
        cards.append(
            f"<div style='background:{pal['card']};border:1px solid {pal['border']};"
            "border-radius:10px;padding:8px;'>" + svg + "</div>")
    grid = (
        "<div style='display:grid;gap:12px;padding:12px;"
        "grid-template-columns:repeat(auto-fit,minmax(340px,1fr));'>"
        + "".join(cards) + "</div>"
    )
    return _page(pal, grid)
