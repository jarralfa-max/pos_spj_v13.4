"""Renderer del dashboard ejecutivo BI (HTML autónomo desde el payload)."""
from modulos.bi_dashboard_view import _fmt_value, render_dashboard_html


def _payload():
    return {
        "kpis": [
            {"key": "ventas_netas", "title": "Ventas netas", "value": 1245680,
             "unit": "$", "direction": "up", "semantic": "positive",
             "delta_pct": 12.6, "formula": "SUM(total)"},
            {"key": "margen", "title": "Margen %", "value": 12.57, "unit": "%",
             "direction": "up", "semantic": "positive", "delta_points": 1.8},
            {"key": "ordenes", "title": "Órdenes", "value": 14592, "unit": "",
             "direction": "up", "semantic": "positive", "delta_pct": 9.7},
        ],
        "charts": {
            "branch_sales": {"kind": "bar", "title": "Ventas por sucursal",
                             "labels": ["A", "B"],
                             "series": [{"name": "Ventas", "color": "#3b82f6",
                                         "values": [463, 312]}], "unit": "$"},
            "payment_methods": {"kind": "donut", "title": "Métodos de pago",
                                "labels": ["Efectivo", "Tarjeta"],
                                "series": [{"name": "Total", "color": "#3b82f6",
                                            "values": [70, 30]}], "unit": "$"},
            "sales_trend": {"kind": "line", "title": "Evolución",
                            "labels": ["ene", "feb"],
                            "series": [{"name": "Ventas", "color": "#3b82f6",
                                        "values": [10, 20]},
                                       {"name": "Utilidad", "color": "#eab308",
                                        "values": [2, 5]}], "unit": "$"},
        },
        "highlights": {
            "top_product": {"key": "top_product", "title": "Producto top",
                            "name": "Pollo entero", "value": 182450,
                            "share_pct": 14.6, "unit": "$"}},
        "alerts": [{"level": "critical", "code": "merma_alta", "title": "Merma alta",
                    "detail": "1.82% de ventas"}],
        "insights": [{"code": "sucursal_top", "title": "Mayor venta en San Bartolo",
                      "detail": "Lidera con $463,120"}],
        "predictions": {"next_week": {"key": "next_week",
                                      "title": "Predicción próxima semana",
                                      "value": 1315000, "unit": "$",
                                      "detail": "~$187,857/día"}},
    }


def test_render_incluye_kpis_charts_y_sidebar():
    html = render_dashboard_html(_payload())
    assert "Ventas netas" in html and "$1,245,680" in html
    assert html.count("<svg") == 3            # 3 charts
    assert "Producto top" in html and "Pollo entero" in html
    assert "Merma alta" in html               # alerta
    assert "Mayor venta en San Bartolo" in html  # insight
    assert "Predicción próxima semana" in html
    # offline: sin red ni scripts
    assert "http://" not in html and "https://" not in html
    assert "<script" not in html


def test_render_escapa_contenido():
    p = _payload()
    p["insights"][0]["title"] = "<b>x</b>"
    html = render_dashboard_html(p)
    assert "<b>x</b>" not in html and "&lt;b&gt;" in html


def test_fmt_value_por_unidad():
    assert _fmt_value(1245680, "$") == "$1,245,680"
    assert _fmt_value(85.4, "$") == "$85.40"
    assert _fmt_value(12.57, "%") == "12.57%"
    assert _fmt_value(6.42, "x") == "6.42x"
    assert _fmt_value(14592, "") == "14,592"


def test_render_payload_vacio_no_rompe():
    html = render_dashboard_html({})
    assert "<html" in html and "<script" not in html


def test_render_section_html():
    from modulos.bi_dashboard_view import render_section_html
    data = {
        "section": "ventas", "title": "Ventas",
        "kpis": [{"title": "Ventas netas", "value": 150, "unit": "$"}],
        "charts": [{"kind": "bar", "title": "Por sucursal", "labels": ["A"],
                    "series": [{"name": "Ventas", "color": "#3b82f6", "values": [150]}],
                    "unit": "$"}],
        "tables": [{"title": "Top productos", "columns": ["Producto", "Ingresos $"],
                    "rows": [["Pollo", "$150.00"]]}],
    }
    html = render_section_html(data)
    assert "Ventas netas" in html and "$150" in html
    assert "<svg" in html
    assert "<table" in html and "Pollo" in html
    assert "https://" not in html and "<script" not in html


def test_render_section_tabla_vacia():
    from modulos.bi_dashboard_view import render_section_html
    html = render_section_html({"kpis": [], "charts": [],
                                "tables": [{"title": "X", "columns": ["A"], "rows": []}]})
    assert "Sin datos" in html
