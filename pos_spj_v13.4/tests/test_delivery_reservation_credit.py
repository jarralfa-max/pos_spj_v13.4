"""Tests for delivery defects 9 (reservation adjustment) and 10 (credit gate).

Defect 9: After confirming real weight/quantity, the inventory soft-lock
(inventory_reservations) must be re-adjusted to the prepared quantity,
idempotently.

Defect 10: Before a delivery order leaves to preparation, if its payment method
leaves a balance owed on the customer's account, the customer's credit must be
validated; insufficient credit blocks preparation.
"""
from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from core.delivery.domain.credit_policy import credit_amount, requires_credit_check
from core.services.reservation_service import ReservationService


# ── Defect 9: ReservationService.adjust_reservation ──────────────────────────

@pytest.fixture
def reservations_db():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """CREATE TABLE inventory_reservations (
            id TEXT PRIMARY KEY,
            branch_id INTEGER,
            product_id INTEGER,
            reserved_qty REAL,
            operation_id TEXT,
            operation_type TEXT,
            expires_at TEXT,
            released INTEGER DEFAULT 0
        )"""
    )
    conn.execute(
        """CREATE TABLE inventario_actual (
            producto_id INTEGER, sucursal_id INTEGER, cantidad REAL
        )"""
    )
    conn.execute("INSERT INTO inventario_actual VALUES (10, 1, 100.0)")
    conn.commit()
    return conn


def _seed_reservation(db, op_id="delivery:1", product_id=10, qty=2.0):
    ReservationService().reserve(
        db, product_id=product_id, qty=qty, operation_id=op_id, branch_id=1
    )


def test_adjust_reservation_updates_reserved_qty(reservations_db):
    """Defect 9: adjusting sets reserved_qty to the prepared value."""
    svc = ReservationService()
    _seed_reservation(reservations_db, qty=2.0)
    rows = svc.adjust_reservation(reservations_db, "delivery:1", 10, 2.35, 1)
    assert rows == 1
    got = reservations_db.execute(
        "SELECT reserved_qty FROM inventory_reservations WHERE operation_id='delivery:1' AND released=0"
    ).fetchone()
    assert abs(got[0] - 2.35) < 1e-9


def test_adjust_reservation_is_idempotent(reservations_db):
    """Defect 9: replaying the same adjustment yields the same absolute state."""
    svc = ReservationService()
    _seed_reservation(reservations_db, qty=2.0)
    svc.adjust_reservation(reservations_db, "delivery:1", 10, 1.80, 1)
    svc.adjust_reservation(reservations_db, "delivery:1", 10, 1.80, 1)
    rows = reservations_db.execute(
        "SELECT reserved_qty FROM inventory_reservations WHERE operation_id='delivery:1' AND released=0"
    ).fetchall()
    assert len(rows) == 1
    assert abs(rows[0][0] - 1.80) < 1e-9


def test_adjust_reservation_ignores_released(reservations_db):
    """Defect 9: a released reservation is not adjusted."""
    svc = ReservationService()
    _seed_reservation(reservations_db, qty=2.0)
    reservations_db.execute(
        "UPDATE inventory_reservations SET released=1 WHERE operation_id='delivery:1'"
    )
    reservations_db.commit()
    rows = svc.adjust_reservation(reservations_db, "delivery:1", 10, 5.0, 1)
    assert rows == 0


def test_adjust_reservation_changes_available_stock(reservations_db):
    """Defect 9: lowering the reservation frees available stock."""
    svc = ReservationService()
    _seed_reservation(reservations_db, qty=10.0)
    before = svc.get_available_stock(reservations_db, 10, 1)  # 100 - 10 = 90
    svc.adjust_reservation(reservations_db, "delivery:1", 10, 4.0, 1)
    after = svc.get_available_stock(reservations_db, 10, 1)   # 100 - 4 = 96
    assert after > before
    assert abs(after - 96.0) < 1e-9


# ── AdjustDeliveryWeightUseCase wiring (defect 9) ────────────────────────────

class _FakeRepo:
    def __init__(self, order, item):
        self._order = order
        self._item = item
        self.applied = None

    def get_order(self, order_id):
        return self._order

    def get_item_for_weight_adjustment(self, order_id, item_id):
        return self._item

    def apply_item_weight_adjustment(self, **kwargs):
        self.applied = kwargs


def test_adjust_weight_calls_reservation_adjuster():
    """Defect 9: accepted adjustment invokes the injected reservation adjuster."""
    from core.delivery.application.adjust_delivery_weight import AdjustDeliveryWeightUseCase

    order = {"estado": "preparacion", "total": 100.0, "sucursal_id": 1, "folio": "DEL-1"}
    item = {"precio_unitario": 10.0, "cantidad": 2.0, "nombre": "Carne", "producto_id": 10}
    repo = _FakeRepo(order, item)

    calls = []

    class _DB:
        def commit(self):
            pass

    uc = AdjustDeliveryWeightUseCase(
        db=_DB(),
        repository=repo,
        recalculate_order_total=lambda _oid: 21.0,
        adjust_reservation=lambda op, pid, qty, branch: calls.append((op, pid, qty, branch)) or 1,
    )
    # prepared within tolerance (2.0 -> 2.1, tolerance 0.2) so it is accepted
    result = uc.execute(order_id=1, item_id=5, prepared_qty=2.1, prepared_by="op", unit="kg")
    assert result["applied"] is True
    assert calls == [("delivery:1", 10, 2.1, 1)]


# ── Defect 10: credit policy ─────────────────────────────────────────────────

def test_requires_credit_check_for_saldo():
    assert requires_credit_check("Anticipo + saldo") is True


def test_requires_credit_check_for_credito():
    assert requires_credit_check("Crédito 30 días") is True


def test_requires_credit_check_false_for_cash():
    assert requires_credit_check("Efectivo al entregar") is False
    assert requires_credit_check("Ya pagado (online)") is False
    assert requires_credit_check("") is False
    assert requires_credit_check(None) is False


def test_credit_amount_subtracts_advance():
    assert credit_amount(Decimal("100"), Decimal("30")) == Decimal("70")


def test_credit_amount_floors_at_zero():
    assert credit_amount(Decimal("50"), Decimal("80")) == Decimal("0")


def test_credit_amount_uses_decimal():
    result = credit_amount(100.50, 0.50)
    assert isinstance(result, Decimal)
    assert result == Decimal("100.00")


# ── ChangeDeliveryStatusUseCase credit gate (defect 10) ──────────────────────

class _CreditRepo:
    def __init__(self, order):
        self._order = order
        self.updated = False

    def get_order(self, order_id):
        return self._order

    def has_pending_adjustment(self, order_id):
        return False

    def update_status(self, *a, **k):
        self.updated = True

    def mark_adjustment_blocked(self, *a, **k):
        pass


class _FakeCredit:
    def __init__(self, ok, reason=""):
        self._ok = ok
        self._reason = reason
        self.called_with = None

    def validate_credit(self, cliente_id, monto):
        self.called_with = (cliente_id, monto)
        return self._ok, self._reason


def _make_uc(order, credit_service):
    from core.delivery.application.change_delivery_status import ChangeDeliveryStatusUseCase

    class _DB:
        def commit(self):
            pass

    return ChangeDeliveryStatusUseCase(
        db=_DB(),
        repository=_CreditRepo(order),
        credit_service=credit_service,
        get_order_items=lambda _oid: [],
    )


def test_credit_insufficient_blocks_preparation():
    """Defect 10: insufficient credit raises and blocks the transition."""
    order = {
        "estado": "pendiente", "pago_metodo": "Anticipo + saldo",
        "cliente_id": 7, "total": 500.0, "anticipo": 100.0, "sucursal_id": 1,
    }
    credit = _FakeCredit(ok=False, reason="Crédito insuficiente")
    uc = _make_uc(order, credit)
    with pytest.raises(ValueError, match="No se puede preparar"):
        uc.execute(1, "preparacion", usuario="op")
    # validated the balance (total - anticipo) = 400
    assert credit.called_with == (7, 400.0)


def test_credit_sufficient_allows_preparation():
    """Defect 10: sufficient credit allows the transition."""
    order = {
        "estado": "pendiente", "pago_metodo": "Anticipo + saldo",
        "cliente_id": 7, "total": 500.0, "anticipo": 100.0, "sucursal_id": 1,
    }
    credit = _FakeCredit(ok=True)
    uc = _make_uc(order, credit)
    uc.execute(1, "preparacion", usuario="op")
    assert uc.repository.updated is True


def test_cash_method_skips_credit_check():
    """Defect 10: cash-on-delivery is not gated by credit."""
    order = {
        "estado": "pendiente", "pago_metodo": "Efectivo al entregar",
        "cliente_id": 7, "total": 500.0, "sucursal_id": 1,
    }
    credit = _FakeCredit(ok=False, reason="should not be called")
    uc = _make_uc(order, credit)
    uc.execute(1, "preparacion", usuario="op")
    assert credit.called_with is None
    assert uc.repository.updated is True


def test_credit_check_skipped_without_cliente_id():
    """Defect 10: no cliente_id → no credit gate (cannot validate an anonymous account)."""
    order = {
        "estado": "pendiente", "pago_metodo": "Anticipo + saldo",
        "cliente_id": None, "total": 500.0, "sucursal_id": 1,
    }
    credit = _FakeCredit(ok=False, reason="x")
    uc = _make_uc(order, credit)
    uc.execute(1, "preparacion", usuario="op")
    assert credit.called_with is None
