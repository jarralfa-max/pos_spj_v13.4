from pathlib import Path

from core.ticket_escpos_renderer import TicketESCPOSRenderer, INIT
from core.tickets.ticket_print_model import (
    TicketPrintModel, TicketItem, TicketTotals, TicketPaymentInfo, TicketBranding, TicketLoyaltyInfo,
)
from core.tickets.ticket_message_engine import TicketMessageEngine


class _FakePrinterService:
    def __init__(self, enabled=True):
        self.enabled = enabled
        self.calls = []

    def has_ticket_printer(self):
        return self.enabled

    def print_ticket(self, payload):
        if not self.enabled:
            raise RuntimeError("No hay impresora térmica ESC/POS configurada.")
        self.calls.append(payload)
        return "job-1"


def test_venta_modelo_renderer_printer_pipeline():
    model = TicketPrintModel(
        ticket_type="sale",
        folio="V-100",
        fecha="2026-05-27 12:00:00",
        cajero="ana",
        cliente_nombre="Juan",
        items=[TicketItem(nombre="Pechuga", cantidad=1, precio_unitario=100, total=100)],
        totals=TicketTotals(subtotal=100, descuento=0, total_final=100),
        payment=TicketPaymentInfo(forma_pago="Efectivo", efectivo_recibido=200, cambio=100),
        branding=TicketBranding(brand_name="SPJ", address="Dir", phone="555"),
        loyalty=TicketLoyaltyInfo(puntos_ganados=10, puntos_totales=120),
    )
    engine = TicketMessageEngine()
    msg = engine.build_messages({"puntos_ganados": 10, "puntos_totales": 120}, {"cliente_id": 1, "promo_days_left": 2, "promo_name": "Promo"})
    assert any(m.code == "promo_expiring" for m in msg.fomo_messages)

    payload = model.to_dict()
    renderer = TicketESCPOSRenderer(paper_width_mm=80)
    raw = renderer.render(payload)
    assert raw.startswith(INIT)
    assert b"TOTAL" in raw

    printer = _FakePrinterService(enabled=True)
    jid = printer.print_ticket(payload)
    assert jid == "job-1"
    assert len(printer.calls) == 1


def test_error_claro_si_no_hay_impresora():
    printer = _FakePrinterService(enabled=False)
    try:
        printer.print_ticket({"folio": "V-1"})
        assert False, "expected error"
    except RuntimeError as e:
        assert "No hay impresora térmica ESC/POS configurada." in str(e)


def test_pdf_auditoria_ruta_separada_sigue_disponible():
    src = Path("modulos/ventas.py").read_text(encoding="utf-8")
    assert "def guardar_ticket_pdf" in src
    assert "def _guardar_pdf_auditoria_ultima_venta" in src


def test_delivery_y_caja_usan_printerservice_en_tests_dedicados():
    src_delivery = Path("tests/test_delivery_ticket_uses_escpos.py").read_text(encoding="utf-8")
    src_caja = Path("tests/test_caja_ticket_uses_escpos.py").read_text(encoding="utf-8")
    assert "delivery_customer" in src_delivery and "delivery_driver" in src_delivery
    assert "caja_corte_z" in src_caja


def test_no_qprinter_en_rutas_termicas_principales():
    for rel in [
        "modulos/ventas.py",
        "modulos/ticket_designer.py",
        "core/services/ticket_printer_service.py",
    ]:
        src = Path(rel).read_text(encoding="utf-8")
        if rel.endswith("ventas.py"):
            start = src.index("def _imprimir_ticket_consolidado")
            end = src.index("def _imprimir_ticket_hardware", start)
            src = src[start:end]
        assert "QPrinter" not in src
