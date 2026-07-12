"""Venta a crédito válida crea CxC, actualiza credit_balance y es idempotente."""
from __future__ import annotations

import pytest

from application.services.customer_credit_service import CustomerCreditService
from backend.shared.ids import new_uuid
from core.events.handlers.finance_handler import CreditSaleFinanceHandler
from tests.integration._born_clean_db import make_db


class _FinanceStub:
    def __init__(self):
        self.asientos = []

    def registrar_asiento(self, **kwargs):
        self.asientos.append(kwargs)


def _customer(conn) -> str:
    cid = new_uuid()
    conn.execute(
        "INSERT INTO clientes (id, nombre, activo, allows_credit, credit_limit, "
        " credit_balance, saldo) VALUES (?, 'Cliente Crédito', 1, 1, 5000, 0, 0)",
        (cid,),
    )
    return cid


def test_credit_sale_creates_cxc_and_updates_balance():
    conn = make_db()
    cid = _customer(conn)
    fin = _FinanceStub()
    svc = CustomerCreditService(conn, fin)
    venta_id, sucursal_id = new_uuid(), new_uuid()

    svc.register_credit_sale(cid, venta_id, "F-100", 750.0, sucursal_id)

    cxc = conn.execute(
        "SELECT id, cliente_id, venta_id, folio, monto_original, saldo_pendiente, "
        " sucursal_id, estado FROM cuentas_por_cobrar WHERE venta_id=?",
        (venta_id,),
    ).fetchone()
    assert cxc is not None
    assert cxc[0], "cuentas_por_cobrar.id debe acuñarse con new_uuid()"
    assert cxc[1] == cid and cxc[3] == "F-100"
    assert cxc[4] == 750.0 and cxc[5] == 750.0
    assert cxc[6] == sucursal_id and cxc[7] == "pendiente"

    row = conn.execute(
        "SELECT credit_balance, saldo FROM clientes WHERE id=?", (cid,)
    ).fetchone()
    assert row[0] == 750.0 and row[1] == 750.0

    # Asiento GL dentro de la misma transacción
    assert len(fin.asientos) == 1
    asiento = fin.asientos[0]
    assert asiento["debe"] == "130.1-cuentas-por-cobrar"
    assert asiento["haber"] == "401.0-ingresos-ventas"
    assert asiento["monto"] == 750.0


def test_credit_sale_is_idempotent_by_venta_id():
    conn = make_db()
    cid = _customer(conn)
    fin = _FinanceStub()
    svc = CustomerCreditService(conn, fin)
    venta_id = new_uuid()

    svc.register_credit_sale(cid, venta_id, "F-101", 100.0, new_uuid())
    svc.register_credit_sale(cid, venta_id, "F-101", 100.0, new_uuid())  # retry

    n = conn.execute(
        "SELECT COUNT(*) FROM cuentas_por_cobrar WHERE venta_id=?", (venta_id,)
    ).fetchone()[0]
    assert n == 1, "la CxC no debe duplicarse al reintentar el evento"

    balance = conn.execute(
        "SELECT credit_balance FROM clientes WHERE id=?", (cid,)
    ).fetchone()[0]
    assert balance == 100.0, "credit_balance no debe duplicarse en el retry"
    assert len(fin.asientos) == 1


def test_handler_aborts_credit_sale_without_customer():
    """CxC nunca se omite en silencio: payload incompleto aborta la venta."""
    conn = make_db()
    handler = CreditSaleFinanceHandler(conn, _FinanceStub())
    with pytest.raises(ValueError, match="no puede omitirse"):
        handler.handle({
            "payment_method": "Crédito",
            "total": 100.0,
            "cliente_id": "",
            "sale_id": new_uuid(),
        })


def test_handler_delegates_to_canonical_service():
    conn = make_db()
    cid = _customer(conn)
    fin = _FinanceStub()
    handler = CreditSaleFinanceHandler(conn, fin)
    venta_id = new_uuid()
    handler.handle({
        "payment_method": "Crédito",
        "total": 300.0,
        "cliente_id": cid,
        "sale_id": venta_id,
        "folio": "F-102",
        "branch_id": new_uuid(),
    })
    row = conn.execute(
        "SELECT saldo_pendiente FROM cuentas_por_cobrar WHERE venta_id=?", (venta_id,)
    ).fetchone()
    assert row and row[0] == 300.0
