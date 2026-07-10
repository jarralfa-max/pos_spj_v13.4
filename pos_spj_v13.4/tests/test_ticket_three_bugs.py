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


def test_escpos_raster_polaridad_negro_imprime():
    """ESC/POS GS v0: el contenido negro debe imprimir (bit 1) y el fondo blanco
    NO (bit 0). Antes se enviaba invertido (fondo negro)."""
    pytest.importorskip("PIL")
    from PIL import Image
    from core.ticket_escpos_renderer import TicketESCPOSRenderer
    r = TicketESCPOSRenderer(paper_width_mm=80)
    im = Image.new("1", (8, 1), 1)   # todo blanco
    im.putpixel((0, 0), 0)           # un pixel negro (MSB)
    raw = r._image_to_escpos_raster(im)
    payload = raw[8:]                # tras la cabecera GS v0 (8 bytes)
    assert payload == bytes([0x80])  # negro→bit1 (imprime), blancos→bit0


def test_logo_fondo_claro_no_se_imprime_completo():
    """Un logo con fondo claro y una figura oscura no debe imprimirse como bloque
    negro: la mayoría de los bits deben quedar apagados (fondo = papel)."""
    pytest.importorskip("PIL")
    import base64, io
    from PIL import Image
    from core.ticket_escpos_renderer import TicketESCPOSRenderer
    img = Image.new("RGB", (64, 64), (244, 244, 244))   # fondo claro
    for y in range(26, 38):
        for x in range(26, 38):
            img.putpixel((x, y), (20, 60, 30))          # figura oscura pequeña
    buf = io.BytesIO(); img.save(buf, "PNG")
    b64 = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    r = TicketESCPOSRenderer(paper_width_mm=80)
    raw = r._render_logo(b64, logo_size="sm")
    assert raw
    payload = raw[8:]
    set_bits = sum(bin(b).count("1") for b in payload)
    total_bits = len(payload) * 8
    # el fondo (mayoría) NO debe imprimir: pocos bits encendidos
    assert set_bits < total_bits * 0.4


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


def test_escpos_bloques_pago_mixto_desglose():
    """El render por bloques (ruta térmica real) muestra el monto por método en
    pago mixto, además de recibido y cambio."""
    from core.ticket_escpos_renderer import TicketESCPOSRenderer
    r = TicketESCPOSRenderer(paper_width_mm=80)
    payload = {
        "folio": "V-1", "fecha": "2026-07-10", "cajero": "Ana",
        "items": [{"name": "Mango", "cantidad": 1, "total": 116.0}],
        "totales": {"total_final": 116.0}, "total": 116.0,
        "pago": {"forma_pago": "Pago Mixto", "efectivo_recibido": 100.0, "tarjeta": 50.0,
                 "cambio": 34.0, "lineas": {"efectivo": 100.0, "tarjeta": 50.0}},
    }
    txt = r.render(payload).decode("cp850", "replace")
    txt = "".join(c if (c.isprintable() or c == "\n") else "" for c in txt)
    assert "Efectivo: $100.00" in txt
    assert "Tarjeta: $50.00" in txt
    assert "Recibido: $100.00" in txt
    assert "Cambio: $34.00" in txt
    assert "Mango" in txt


def test_html_desglose_pago_mixto():
    from core.engines.template_engine import TicketTemplateEngine
    eng = TicketTemplateEngine(None)
    out = eng.generar_ticket("D={{pago_desglose}}", {
        "totales": {"total_final": 150},
        "pago": {"forma_pago": "Pago Mixto", "lineas": {"efectivo": 100.0, "tarjeta": 50.0}},
    })
    assert "Efectivo" in out and "$100.00" in out
    assert "Tarjeta" in out and "$50.00" in out


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
