# tests/test_ticket_three_bugs.py
"""Regresión de 3 bugs del ticket impreso:

1. Fondo del logo se imprime → el raster ESC/POS quita fondos sólidos de color.
2. No muestra el nombre del producto → nombre robusto (name/nombre) en todos los
   renderizadores (HTML + ESC/POS + resolución de items).
3. No muestra recibido/cambio → se muestran en la vista de texto ESC/POS y en el
   ctx/plantilla HTML.
"""
import io

import pytest


# ── Bug 1: fondo sólido de color del logo no debe imprimirse ────────────────────
def test_logo_fondo_solido_color_se_vuelve_blanco():
    pytest.importorskip("PIL")
    from PIL import Image
    from core.ticket_escpos_renderer import TicketESCPOSRenderer

    # logo 40x40 con fondo AZUL sólido (oscuro → imprimiría) y una marca clara
    img = Image.new("RGB", (40, 40), (0, 0, 180))
    for y in range(15, 25):
        for x in range(15, 25):
            img.putpixel((x, y), (255, 255, 255))
    r = TicketESCPOSRenderer(paper_width_mm=80)
    l = r._compose_logo_on_white(img)[0]
    # las esquinas (fondo azul) deben quedar blancas (255) → no imprimen
    for xy in [(0, 0), (39, 0), (0, 39), (39, 39)]:
        assert l.getpixel(xy) == 255


def test_logo_fondo_blanco_intacto():
    pytest.importorskip("PIL")
    from PIL import Image
    from core.ticket_escpos_renderer import TicketESCPOSRenderer
    img = Image.new("RGB", (30, 30), (255, 255, 255))
    img.putpixel((15, 15), (0, 0, 0))
    r = TicketESCPOSRenderer(paper_width_mm=80)
    l = r._compose_logo_on_white(img)[0]
    assert l.getpixel((0, 0)) == 255           # blanco sigue blanco
    assert l.getpixel((15, 15)) < 128          # el punto negro se conserva


# ── Bug 2: nombre del producto ─────────────────────────────────────────────────
def test_resolve_items_preserva_nombre_desde_name(monkeypatch):
    """_resolve_sale_items debe tomar el nombre de 'name' (clave del UC) si no hay
    'nombre'."""
    import sqlite3
    from migrations import engine
    from core.services.sales_service import SalesService

    conn = sqlite3.connect(":memory:"); conn.row_factory = sqlite3.Row
    engine.up(conn); conn.commit()
    svc = SalesService(conn, None, None, None, None, None, None, None, None, None, None, None)

    class _Line:
        product_id = "p1"; qty = 2.0; name = ""; mode = "direct"; source_product_id = "p1"

    monkeypatch.setattr(svc._fulfillment, "resolve_item", lambda pid, qty, bid: [_Line()])
    out = svc._resolve_sale_items([{"product_id": "p1", "qty": 2.0, "name": "Mango Enchilado"}], "s1")
    assert out and out[0]["nombre"] == "Mango Enchilado"


def test_html_items_usan_nombre_robusto():
    from core.engines.template_engine import TicketTemplateEngine
    eng = TicketTemplateEngine(None)
    filas = eng._generar_filas_items([{"name": "Pollo Asado", "cantidad": 1, "precio_unitario": 90, "total": 90}])
    assert "Pollo Asado" in filas


def test_escpos_text_muestra_nombre():
    from core.ticket_escpos_renderer import TicketESCPOSRenderer
    r = TicketESCPOSRenderer(paper_width_mm=80)
    txt = r.render_text_preview({"items": [{"name": "Chicharrón", "cantidad": 1, "total": 50}],
                                 "totales": {"total_final": 50}})
    assert "Chicharrón" in txt


# ── Bug 3: recibido y cambio ────────────────────────────────────────────────────
def test_escpos_text_muestra_recibido_y_cambio():
    from core.ticket_escpos_renderer import TicketESCPOSRenderer
    r = TicketESCPOSRenderer(paper_width_mm=80)
    txt = r.render_text_preview({
        "items": [{"nombre": "X", "cantidad": 1, "total": 116}],
        "totales": {"total_final": 116},
        "pago": {"forma_pago": "Efectivo", "efectivo_recibido": 200.0, "cambio": 84.0},
    })
    assert "Recibido: $200.00" in txt
    assert "Cambio: $84.00" in txt


def test_html_ctx_recibido_y_cambio_desde_pago_dict():
    from core.engines.template_engine import TicketTemplateEngine
    eng = TicketTemplateEngine(None)
    tpl = "R={{recibido}} E={{efectivo}} C={{cambio}} FP={{forma_pago}}"
    out = eng.generar_ticket(tpl, {
        "totales": {"total_final": 116},
        "pago": {"forma_pago": "Efectivo", "efectivo_recibido": 200.0, "cambio": 84.0},
    })
    assert "R=$200.00" in out and "E=$200.00" in out
    assert "C=$84.00" in out
    assert "Efectivo" in out
