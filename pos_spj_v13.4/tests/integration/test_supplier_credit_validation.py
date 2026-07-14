"""Bug 8: Compras valida el crédito del proveedor antes de autorizar a crédito."""
from __future__ import annotations

import pytest

from application.services.supplier_credit_service import SupplierCreditService
from backend.shared.ids import new_uuid
from core.services.purchase_service import PurchaseService
from tests.integration._born_clean_db import make_db


def _supplier(conn, *, activo=1, limite=0.0) -> str:
    sid = new_uuid()
    conn.execute(
        "INSERT INTO proveedores (id, nombre, activo, limite_credito) VALUES (?, 'Prov', ?, ?)",
        (sid, activo, limite),
    )
    return sid


def _cxp(conn, supplier_id, balance):
    conn.execute(
        "INSERT INTO accounts_payable (id, folio, supplier_id, concepto, amount, balance, status) "
        "VALUES (?, ?, ?, 'x', ?, ?, 'pendiente')",
        (new_uuid(), f"CXP-{balance}", supplier_id, balance, balance),
    )


def test_credit_without_supplier_fails():
    conn = make_db()
    svc = SupplierCreditService(conn)
    ok, msg = svc.validate_credit("", 100.0)
    assert not ok and "proveedor válido" in msg


def test_supplier_without_credit_line_fails():
    conn = make_db()
    svc = SupplierCreditService(conn)
    sid = _supplier(conn, limite=0.0)
    ok, msg = svc.validate_credit(sid, 100.0)
    assert not ok and "línea de crédito" in msg


def test_inactive_supplier_fails():
    conn = make_db()
    svc = SupplierCreditService(conn)
    sid = _supplier(conn, activo=0, limite=1000.0)
    ok, msg = svc.validate_credit(sid, 100.0)
    assert not ok and "inactivo" in msg


def test_insufficient_available_credit_fails():
    conn = make_db()
    svc = SupplierCreditService(conn)
    sid = _supplier(conn, limite=1000.0)
    _cxp(conn, sid, 900.0)  # ya debe 900
    ok, msg = svc.validate_credit(sid, 200.0)  # disponible 100 < 200
    assert not ok and "insuficiente" in msg


def test_valid_supplier_credit_passes():
    conn = make_db()
    svc = SupplierCreditService(conn)
    sid = _supplier(conn, limite=1000.0)
    _cxp(conn, sid, 300.0)
    ok, msg = svc.validate_credit(sid, 500.0)  # disponible 700 ≥ 500
    assert ok and msg == ""
    assert svc.available_credit(sid) == 700.0


def test_purchase_service_blocks_over_limit_credit_purchase():
    conn = make_db()
    sid = _supplier(conn, limite=100.0)
    svc = PurchaseService(conn, purchase_repo=None, inventory_service=None,
                          finance_service=None)
    with pytest.raises(ValueError, match="insuficiente|línea de crédito"):
        # amount_paid=0 → toda la compra a crédito, excede el límite de 100
        svc.register_purchase(
            provider_id=sid, branch_id=new_uuid(), user="u",
            items=[{"product_id": new_uuid(), "qty": 1, "unit_cost": 500.0}],
            payment_method="CREDITO", amount_paid=0.0,
        )
