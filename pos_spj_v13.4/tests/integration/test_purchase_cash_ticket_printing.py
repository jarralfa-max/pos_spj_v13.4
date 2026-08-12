"""Impresion de recibos de compra/caja: ruta canonica y fallo no destructivo."""
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


def test_cash_printing_uses_canonical_queue_and_audit_ports():
    """Caja ya no usa CajaTicketService; imprime por use case + cola/auditoria."""
    from backend.application.cash_register.printing import (
        CashPrintAuditRepository,
        CashPrintQueue,
        PrintCashDocumentUseCase,
    )

    src = (APP_ROOT / "backend" / "application" / "cash_register" / "printing.py").read_text(encoding="utf-8")
    assert "CajaTicketService" not in src
    assert CashPrintQueue
    assert CashPrintAuditRepository
    assert PrintCashDocumentUseCase


def test_sales_ui_delegates_printing_to_printer_service():
    text = (APP_ROOT / "modulos" / "ventas.py").read_text(encoding="utf-8")
    code = "\n".join(line for line in text.splitlines() if not line.strip().startswith("#"))
    assert "from escpos.printer import Usb" not in code
    assert "printer_service" in code
    assert "La venta fue completada, pero el ticket no se imprimi" in text
