"""Plantilla del ticket de venta.

Reemplaza `core/engines/template_engine.py`. El formato `{{campo}}` y los campos
que la plantilla por omisión debe traer no se eligieron al reescribirla: los
fijan `tests/test_sales_service_single_event_flow.py` y
`tests/integration/test_sale_ticket_default_template.py`.
"""
from __future__ import annotations

import pytest

from backend.infrastructure.printing.ticket_template import (
    TicketTemplateEngine,
    default_ticket_template,
)

VENTA = {
    "folio": "F-900",
    "venta_id": "0198aaaa-bbbb-7ccc-8ddd-eeeeffff0001",
    "fecha": "2026-07-12 10:00:00",
    "cajero": "ana",
    "nombre_empresa": "SPJ Carnes",
    "sucursal_nombre": "Centro",
    "sucursal_direccion": "Av. Uno 123",
    "sucursal_telefono": "555-0000",
    "forma_pago": "Efectivo",
    "totales": {"subtotal": 100.0, "descuento": 0.0, "total_final": 100.0},
    "items": [{"nombre": "Pollo", "cantidad": 1, "precio_unitario": 100.0, "total": 100.0}],
}


def _render(datos=None, template=None, mensaje=""):
    return TicketTemplateEngine(db_conn=None).generar_ticket(
        template or default_ticket_template(), VENTA if datos is None else datos,
        mensaje_psicologico=mensaje)


# ── contrato de la plantilla por omisión ────────────────────────────────────
@pytest.mark.parametrize("campo", [
    "nombre_empresa", "sucursal_nombre", "folio", "fecha", "cajero", "total", "forma_pago",
])
def test_the_default_template_carries_every_required_field(campo):
    assert "{{" + campo + "}}" in default_ticket_template()


def test_a_complete_ticket_renders_its_data():
    html = _render(mensaje="Gracias por su compra")
    for esperado in ("F-900", "Centro", "ana", "SPJ Carnes", "Pollo",
                     "Gracias por su compra"):
        assert esperado in html


def test_no_placeholder_survives_a_complete_render():
    """Un ticket impreso con "{{total}}" parece un dato literal."""
    assert "{{" not in _render()


def test_the_commercial_folio_is_printed_not_the_internal_uuid():
    html = _render()
    assert "F-900" in html
    assert VENTA["venta_id"] not in html


# ── importes ────────────────────────────────────────────────────────────────
def test_the_total_is_the_amount_actually_charged():
    """`total` sale de `total_final`, no del subtotal antes del descuento."""
    html = _render({**VENTA, "totales": {"subtotal": 100.0, "descuento": 25.0,
                                         "total_final": 75.0}})
    assert "$75.00" in html


def test_amounts_are_formatted_as_money():
    assert "$100.00" in _render()


def test_an_unreadable_amount_shows_as_zero_not_as_text():
    """Un ticket con "Total: abc" parece un precio, y nadie revisa un ticket
    impreso contra la base."""
    html = _render({**VENTA, "totales": {"total_final": "no-es-un-numero"}})
    assert "$0.00" in html
    assert "no-es-un-numero" not in html


def test_thousands_are_readable():
    html = _render({**VENTA, "totales": {"total_final": 12345.6}})
    assert "$12,345.60" in html


# ── renglones ───────────────────────────────────────────────────────────────
def test_every_line_of_the_sale_is_printed():
    html = _render({**VENTA, "items": [
        {"nombre": "Pollo", "cantidad": 2, "total": 200.0},
        {"nombre": "Res", "cantidad": 1, "total": 150.0},
    ]})
    assert "Pollo" in html and "Res" in html
    assert "$200.00" in html and "$150.00" in html


def test_a_sale_without_lines_still_renders():
    """Una devolución total o un ticket de sólo cargos no tiene renglones."""
    html = _render({**VENTA, "items": []})
    assert "F-900" in html and "{{" not in html


def test_a_product_name_cannot_break_the_ticket_html():
    """Un nombre con `<` o `&` rompería el HTML del ticket entero."""
    html = _render({**VENTA, "items": [
        {"nombre": "Costilla <b>especial</b> & más", "cantidad": 1, "total": 10.0}]})
    assert "<b>especial</b>" not in html
    assert "&lt;b&gt;especial" in html


def test_a_malformed_line_is_skipped_not_crashed():
    html = _render({**VENTA, "items": ["no es un diccionario",
                                       {"nombre": "Pollo", "cantidad": 1, "total": 10.0}]})
    assert "Pollo" in html


# ── plantillas del usuario ──────────────────────────────────────────────────
def test_a_user_template_uses_the_same_placeholder_format():
    """El formato que ya guardaron las instalaciones con el diseñador."""
    assert _render(template="<html>{{folio}}</html>") == "<html>F-900</html>"


def test_whitespace_inside_a_placeholder_is_tolerated():
    """Lo teclea cualquiera al editar una plantilla a mano."""
    assert _render(template="{{ folio }}") == "F-900"


def test_an_unknown_placeholder_renders_empty_instead_of_literal():
    """"Total: " se ve roto de inmediato; "Total: {{no_existe}}" parece un dato."""
    assert _render(template="X{{campo_inventado}}Y") == "XY"


def test_an_empty_template_does_not_crash():
    # Se llama al motor directamente: el ayudante `_render` trata una plantilla
    # vacía como "usa la de omisión", que es lo contrario de lo que se prueba.
    assert TicketTemplateEngine(db_conn=None).generar_ticket("", VENTA) == ""


def test_a_none_template_does_not_crash():
    assert TicketTemplateEngine(db_conn=None).generar_ticket(None, VENTA) == ""


def test_rendering_never_reads_the_database():
    """El mismo ticket reimpreso mañana tiene que salir igual: si el motor
    leyera de la base al renderizar, un cambio posterior lo alteraría."""
    class _ConexionQueExplota:
        def execute(self, *_a, **_k):
            raise AssertionError("el motor no debe consultar la base al renderizar")

    engine = TicketTemplateEngine(db_conn=_ConexionQueExplota())
    assert "F-900" in engine.generar_ticket(default_ticket_template(), VENTA)
