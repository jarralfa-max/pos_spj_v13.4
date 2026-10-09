"""CASH-26 bloque 2 — el cajón se abre de verdad.

Medido 2026-10-07: Caja usaba `StubCashHardwareGateway` (registraba la
apertura y el cajón nunca se abría) y el POS no abría el cajón al cobrar. El
cajón va conectado a la impresora del ticket y se abre con el pulso ESC p.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.hardware import CashHardwareError
from backend.application.cash_register.sales_integration import CashSalesIntegrationService
from backend.infrastructure.hardware.cash_drawer_gateway import (
    DRAWER_KICK,
    PrinterKickCashDrawerGateway,
)
from backend.infrastructure.integrations.sales_cash_drawer_client import SalesCashDrawerGateway
from backend.infrastructure.printing.transport import PrintTransport
from backend.shared.ids import new_uuid
from tests.integration.cash_register.test_cash_cut_printing import (  # noqa: F401 - fixture
    _caja,
    _ticket_printer,
    conn,
)


class _Allow:
    def has_permission(self, *_args, **_kwargs):
        return True

    def can_access_branch(self, *_args, **_kwargs):
        return True


@pytest.fixture
def sent(monkeypatch):
    enviados = []
    monkeypatch.setattr(PrintTransport, "send",
                        staticmethod(lambda data, *a, **k: enviados.append(data) or True))
    return enviados


def _ids(conn):
    user_id, branch_id = conn.execute(
        "SELECT id, sucursal_id FROM usuarios WHERE usuario='duena'").fetchone()
    drawer_id = conn.execute("SELECT id FROM cash_drawers").fetchone()[0]
    return user_id, branch_id, drawer_id


def test_caja_opens_the_drawer_through_the_ticket_printer(conn, sent):
    _ticket_printer(conn)
    caja = _caja(conn)
    user_id, branch_id, drawer_id = _ids(conn)
    caja.open_cash_shift(opening_amount=Decimal("0"))
    caja.open_cash_drawer_hardware(drawer_id=drawer_id, reason="Cambio de rollo")
    assert sent == [DRAWER_KICK]
    assert conn.execute("SELECT COUNT(*) FROM cash_domain_events"
                        " WHERE event_name='CASH_DRAWER_OPENED'").fetchone()[0] == 1


def test_without_a_ticket_printer_the_failure_is_recorded_and_explained(conn, sent):
    _user_id, _branch_id, drawer_id = _ids(conn)
    gateway = PrinterKickCashDrawerGateway(conn)
    with pytest.raises(CashHardwareError, match="Ticket de venta"):
        gateway.open_drawer(drawer_id)
    diagnostic = gateway.diagnose(drawer_id)
    assert not diagnostic.connected and "Ticket de venta" in diagnostic.message
    assert sent == []


def test_diagnose_names_the_printer_that_opens_the_drawer(conn):
    _ticket_printer(conn)
    _user_id, _branch_id, drawer_id = _ids(conn)
    diagnostic = PrinterKickCashDrawerGateway(conn).diagnose(drawer_id)
    assert diagnostic.connected and "PRN-01" in diagnostic.message
    register_id = conn.execute("SELECT id FROM cash_registers").fetchone()[0]
    assert not PrinterKickCashDrawerGateway(conn).diagnose(register_id).connected


def test_a_cash_sale_opens_the_drawer_and_a_card_sale_does_not(conn, sent):
    _ticket_printer(conn)
    caja = _caja(conn)
    user_id, branch_id, _drawer = _ids(conn)
    caja.open_cash_shift(opening_amount=Decimal("0"))
    drawer = SalesCashDrawerGateway(
        CashAuthorizationPolicy(permissions=_Allow(), scopes=_Allow()),
        PrinterKickCashDrawerGateway(conn))
    efectivo, tarjeta = new_uuid(), new_uuid()
    for sale_id, tipo in ((efectivo, "CASH"), (tarjeta, "CARD")):
        line = {"type": tipo, "amount": "120.00"}
        if tipo == "CARD":
            line["reference"] = "AUT-1"
        CashSalesIntegrationService().record_completed_sale(
            conn, sale_id=sale_id, branch_id=branch_id, cashier_user_id=user_id,
            operation_id=new_uuid(), payment_lines=[line])
    conn.commit()
    assert drawer.open_for_cash_sale(conn, sale_id=efectivo, branch_id=branch_id,
                                     actor_user_id=user_id, operation_id=new_uuid())
    assert not drawer.open_for_cash_sale(conn, sale_id=tarjeta, branch_id=branch_id,
                                         actor_user_id=user_id, operation_id=new_uuid())
    assert sent == [DRAWER_KICK]
