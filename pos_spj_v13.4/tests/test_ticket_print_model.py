from core.tickets.ticket_print_model import (
    TicketPrintModel,
    TicketItem,
    TicketTotals,
    TicketPaymentInfo,
    TicketBranding,
    TicketLayoutConfig,
)


def _base_model(ticket_type: str = "sale"):
    return TicketPrintModel(
        ticket_type=ticket_type,
        folio="V-001",
        fecha="2026-05-26 10:00:00",
        cajero="admin",
        cliente_nombre="Cliente",
        items=[TicketItem(nombre="Prod", cantidad=1, precio_unitario=10, total=10)],
        totals=TicketTotals(subtotal=10, descuento=0, total_final=10),
        payment=TicketPaymentInfo(forma_pago="Efectivo", efectivo_recibido=20, cambio=10),
        branding=TicketBranding(brand_name="SPJ", address="Dir", phone="123"),
    )


def test_create_sale_ticket_model():
    m = _base_model("sale")
    assert m.ticket_type == "sale"
    assert m.totals.total_final == 10


def test_create_delivery_ticket_model():
    m = _base_model("delivery_customer")
    assert m.ticket_type == "delivery_customer"


def test_layout_58mm_calculates_32_chars():
    l = TicketLayoutConfig(paper_width_mm=58)
    assert l.chars_per_line == 32


def test_layout_80mm_calculates_48_chars():
    l = TicketLayoutConfig(paper_width_mm=80)
    assert l.chars_per_line == 48


def test_defaults_are_safe():
    l = TicketLayoutConfig()
    assert l.feed_lines == 4
    assert l.cut_type == "partial"
    assert l.show_logo is True


def test_serialization_roundtrip_basic():
    m = _base_model("sale")
    d = m.to_dict()
    restored = TicketPrintModel.from_dict(d)
    assert restored.folio == "V-001"
    assert restored.totals.total_final == 10
    assert restored.branding.brand_name == "SPJ"
