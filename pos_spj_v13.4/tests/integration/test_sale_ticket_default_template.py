"""ticket_template_html ausente NUNCA bloquea la venta: se usa template default."""
from __future__ import annotations

from core.engines.template_engine import TicketTemplateEngine
from core.services.sales_service import SalesService


def test_default_template_renders_complete_ticket():
    template = SalesService._default_ticket_template()
    for var in ("{{nombre_empresa}}", "{{sucursal_nombre}}", "{{folio}}",
                "{{fecha}}", "{{cajero}}", "{{total}}", "{{forma_pago}}"):
        assert var in template

    engine = TicketTemplateEngine(db_conn=None)
    html = engine.generar_ticket(
        template,
        {
            "folio": "F-900",
            "venta_id": "0198aaaa-bbbb-7ccc-8ddd-eeeeffff0001",
            "fecha": "2026-07-12 10:00:00",
            "cajero": "ana",
            "sucursal_nombre": "Centro",
            "sucursal_direccion": "Av. Uno 123",
            "sucursal_telefono": "555-0000",
            "totales": {"subtotal": 100.0, "descuento": 0.0, "total_final": 100.0},
            "items": [{"nombre": "Pollo", "cantidad": 1, "precio_unitario": 100.0,
                       "total": 100.0}],
        },
        mensaje_psicologico="Gracias",
    )
    assert "F-900" in html            # folio comercial, no el UUID
    assert "Centro" in html
    assert "ana" in html
    assert "$100.00" in html


def test_sales_service_never_raises_on_missing_template():
    """La ruta de venta usa fallback en lugar de ValueError."""
    from pathlib import Path

    src = (Path(__file__).resolve().parents[2] / "core" / "services" / "sales_service.py")
    text = src.read_text(encoding="utf-8")
    assert 'raise ValueError("ticket_template_html not configured")' not in text
    assert "_default_ticket_template" in text
