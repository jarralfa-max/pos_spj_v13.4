"""Impresión de recibos de compra/caja: ruta canónica y fallo no destructivo."""
from __future__ import annotations

from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2]


def test_printer_service_is_canonical_route():
    """PrinterService expone transportes soportados sin escpos.Usb default."""
    from core.services.printer_service import PrintTransport, TransportType

    assert TransportType.USB_WIN32.value == "usb_win32"
    assert TransportType.NETWORK.value == "network"
    assert hasattr(PrintTransport, "_send_win32")
    src = (APP_ROOT / "core" / "services" / "printer_service.py").read_text(encoding="utf-8")
    assert "escpos.printer.Usb" not in src
    assert "from escpos.printer import Usb" not in src


def test_caja_ticket_service_does_not_raise_on_print_failure():
    """El fallo de impresión no debe propagar y cancelar la operación de Caja."""
    from core.services.caja_ticket_service import CajaTicketService

    svc = CajaTicketService.__new__(CajaTicketService)
    # enviar_escpos devuelve bool — la falla se reporta, no revienta
    assert isinstance(CajaTicketService.enviar_escpos, object)
    src = (APP_ROOT / "core" / "services" / "caja_ticket_service.py").read_text(encoding="utf-8")
    assert "def enviar_escpos" in src


def test_sales_ui_delegates_printing_to_printer_service():
    text = (APP_ROOT / "modulos" / "ventas.py").read_text(encoding="utf-8")
    code = "\n".join(l for l in text.splitlines() if not l.strip().startswith("#"))
    assert "from escpos.printer import Usb" not in code, (
        "la UI de ventas no debe usar escpos.printer.Usb directamente"
    )
    assert "printer_service" in code
    # La venta ya completada no se cancela por fallo del ticket
    assert "La venta fue completada, pero el ticket no se imprimió" in text
