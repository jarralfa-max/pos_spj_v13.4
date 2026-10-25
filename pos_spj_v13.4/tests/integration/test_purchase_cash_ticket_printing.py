"""Impresion de recibos de compra/caja: ruta canonica y fallo no destructivo."""
from __future__ import annotations

from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2]


# `test_printer_service_is_canonical_route` y `test_sales_ui_delegates_printing_to_
# printer_service` leían `core/services/printer_service.py` y `modulos/ventas.py`,
# retirados con el POS heredado. La impresión de tickets de venta la prueban
# `tests/integration/document_output/` y la de Caja, la prueba de abajo.


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

