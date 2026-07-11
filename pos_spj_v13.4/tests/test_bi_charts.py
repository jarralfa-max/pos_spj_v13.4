"""Bug 4 — gráficas del dashboard BI offline (SVG embebido, sin CDN).

Verifica que el generador de gráficas produce SVG autónomo (sin dependencias de
red) y maneja datos vacíos con un placeholder en vez de romperse.
"""
from modulos.bi_charts import (
    bar_chart_html, line_chart_html, hbar_chart_html, donut_chart_html,
    dashboard_html,
)


def test_bar_chart_es_svg_autonomo_sin_cdn():
    html = bar_chart_html("Ventas", ["A", "B", "C"], [10, 20, 5])
    assert "<svg" in html and "</svg>" in html
    assert "Ventas" in html
    # sin dependencias de red
    assert "http://" not in html and "https://" not in html
    assert "<script" not in html
    # una barra por dato
    assert html.count("<rect") == 3


def test_bar_chart_escapa_labels():
    html = bar_chart_html("T", ["<b>x</b>"], [5])
    assert "<b>x</b>" not in html
    assert "&lt;b&gt;" in html


def test_bar_chart_vacio_muestra_placeholder():
    html = bar_chart_html("Sin nada", [], [])
    assert "Sin datos para graficar" in html
    assert "<svg" in html


def test_line_chart_polyline_y_puntos():
    html = line_chart_html("Forecast", ["2026-07-01", "2026-07-02"], [100, 150])
    assert "<polyline" in html
    assert html.count("<circle") == 2
    assert "https://" not in html


def test_bar_chart_todo_cero_no_rompe():
    html = bar_chart_html("Ceros", ["A", "B"], [0, 0])
    assert "<svg" in html  # no lanza excepción


def test_hbar_y_donut_offline():
    h = hbar_chart_html("Top", ["A", "B"], [10, 20])
    assert "<rect" in h and "https://" not in h
    d = donut_chart_html("Pagos", ["Efectivo", "Tarjeta"], [70, 30])
    assert "<path" in d and "https://" not in d and "<script" not in d


def test_dashboard_html_compone_varios_paneles():
    panels = [
        {"kind": "bar", "title": "Sucursal", "labels": ["A"], "values": [5]},
        {"kind": "hbar", "title": "Top", "labels": ["X"], "values": [3]},
        {"kind": "donut", "title": "Pagos", "labels": ["Ef"], "values": [9]},
        {"kind": "line", "title": "Evol", "labels": ["ene", "feb"],
         "series": [("Ventas", [1, 2], "#3b82f6")]},
    ]
    html = dashboard_html(panels)
    assert html.count("<svg") == 4
    assert "grid-template-columns" in html
    assert "https://" not in html and "<script" not in html
