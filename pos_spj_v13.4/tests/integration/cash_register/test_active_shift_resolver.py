"""SDLC-ARQ-SHIFT-001: `ActiveShiftResolver` sobre el esquema real de Caja."""
import importlib
import sqlite3

import pytest

from backend.application.cash_register.active_shift_resolver import ActiveShiftResolver
from backend.domain.cash_register.enums import CashShiftOperability
from backend.domain.cash_register.exceptions import (
    CashShiftClosingError, CashShiftNotOpenError, CashShiftSuspendedError,
)
from backend.shared.ids import new_uuid

_NOW = "2026-08-13T12:00:00+00:00"


@pytest.fixture()
def db():
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys=ON")
    importlib.import_module(
        "migrations.standalone.175_cash_register_bounded_context_schema").run(connection)
    yield connection
    connection.close()


def _devices(db, branch):
    register, drawer, terminal = new_uuid(), new_uuid(), new_uuid()
    tag = register[-6:]
    db.execute("INSERT INTO cash_registers VALUES(?,?,?,?,?,?,?)",
               (register, branch, f"Caja {tag}", "ACTIVE", None, _NOW, _NOW))
    db.execute("INSERT INTO cash_drawers VALUES(?,?,?,?,?,?,?)",
               (drawer, branch, register, f"Cajón {tag}", "ACTIVE", _NOW, _NOW))
    db.execute("INSERT INTO pos_terminals VALUES(?,?,?,?,?,?,?)",
               (terminal, branch, register, f"POS {tag}", "ACTIVE", _NOW, _NOW))
    return register, drawer, terminal


def _shift(db, *, branch, cashier, status, opened_at=_NOW, business_date=None):
    register, drawer, terminal = _devices(db, branch)
    shift_id = new_uuid()
    db.execute(
        """INSERT INTO cash_shifts
        (id,branch_id,register_id,drawer_id,terminal_id,cashier_user_id,
         opening_amount,opening_operation_id,business_date,status,opened_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (shift_id, branch, register, drawer, terminal, cashier, "0", new_uuid(),
         business_date, status, opened_at))
    return shift_id, register


def test_for_cashier_returns_any_active_status_and_respects_branch(db):
    branch, other_branch, cashier = new_uuid(), new_uuid(), new_uuid()
    shift_id, register = _shift(db, branch=branch, cashier=cashier, status="SUSPENDED")
    resolver = ActiveShiftResolver(db)
    found = resolver.for_cashier(cashier_user_id=cashier)
    assert (found.id, found.status, found.register_id) == (shift_id, "SUSPENDED", register)
    assert found.operability is CashShiftOperability.MUST_RESUME
    assert resolver.for_cashier(cashier_user_id=cashier, branch_id=branch).id == shift_id
    assert resolver.for_cashier(cashier_user_id=cashier, branch_id=other_branch) is None
    assert resolver.for_resource(column="register_id", value=register).id == shift_id
    assert resolver.busy_register_ids(branch_id=branch) == {register}


def test_final_statuses_are_not_active(db):
    branch, cashier = new_uuid(), new_uuid()
    _shift(db, branch=branch, cashier=cashier, status="FORCE_CLOSED")
    _shift(db, branch=branch, cashier=cashier, status="CANCELLED")
    resolver = ActiveShiftResolver(db)
    assert resolver.for_cashier(cashier_user_id=cashier) is None
    assert resolver.busy_register_ids(branch_id=branch) == set()
    assert resolver.count_active(branch_id=branch) == 0


@pytest.mark.parametrize("status, error, words", [
    ("SUSPENDED", CashShiftSuspendedError, "suspendido"),
    ("CLOSING", CashShiftClosingError, "abre un turno nuevo"),
    ("PENDING_COUNT", CashShiftClosingError, "abre un turno nuevo"),
])
@pytest.mark.parametrize("purpose", ["sale", "refund"])
def test_require_operable_identifies_the_blocking_shift(db, status, error, words, purpose):
    branch, cashier = new_uuid(), new_uuid()
    shift_id, _ = _shift(db, branch=branch, cashier=cashier, status=status)
    resolver = ActiveShiftResolver(db)
    with pytest.raises(error) as caught:
        resolver.require_operable(branch_id=branch, cashier_user_id=cashier, purpose=purpose)
    assert (caught.value.shift_id, caught.value.status) == (shift_id, status)
    assert words in str(caught.value)
    assert resolver.operability_problem(
        branch_id=branch, cashier_user_id=cashier, purpose=purpose) == str(caught.value)


def test_require_operable_returns_the_open_shift(db):
    branch, cashier = new_uuid(), new_uuid()
    shift_id, _ = _shift(db, branch=branch, cashier=cashier, status="OPEN")
    resolver = ActiveShiftResolver(db)
    assert resolver.require_operable(branch_id=branch, cashier_user_id=cashier).id == shift_id
    assert resolver.operability_problem(branch_id=branch, cashier_user_id=cashier) is None


def test_no_shift_and_no_schema_fail_closed(db):
    branch, cashier = new_uuid(), new_uuid()
    resolver = ActiveShiftResolver(db)
    with pytest.raises(CashShiftNotOpenError) as caught:
        resolver.require_operable(branch_id=branch, cashier_user_id=cashier)
    assert caught.value.shift_id is None
    assert "No tienes un turno de caja abierto" in resolver.operability_problem(
        branch_id=branch, cashier_user_id=cashier)
    bare = sqlite3.connect(":memory:")
    try:
        assert "necesitas tu turno" in ActiveShiftResolver(bare).operability_problem(
            branch_id=branch, cashier_user_id=cashier, purpose="refund")
    finally:
        bare.close()


def test_count_active_filters_by_branch_and_business_date(db):
    branch, other = new_uuid(), new_uuid()
    _shift(db, branch=branch, cashier=new_uuid(), status="OPEN", business_date="2026-08-01")
    _shift(db, branch=branch, cashier=new_uuid(), status="CLOSING", business_date="2026-08-20")
    _shift(db, branch=other, cashier=new_uuid(), status="SUSPENDED",
           opened_at="2026-07-31T23:00:00+00:00")
    resolver = ActiveShiftResolver(db)
    assert resolver.count_active() == 3
    assert resolver.count_active(branch_id=branch) == 2
    assert resolver.count_active(business_date_until="2026-08-10") == 2


def test_repository_rejects_unfiltered_or_unknown_resource_lookup(db):
    from backend.infrastructure.db.repositories.cash_register.repositories import (
        CashShiftRepository,
    )
    with pytest.raises(ValueError):
        CashShiftRepository(db).find_active()
    with pytest.raises(ValueError):
        CashShiftRepository(db).find_active(column="status", value="OPEN")
