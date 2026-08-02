"""P0-B (§6.3) — rebuild balances from the ledger + validate projection drift.

The ledger is the source of truth; balances are reconstructable. A rebuild replays
the whole ledger and must match the live projection (zero drift); a corrupted
balance is detected by the validator.
"""

from decimal import Decimal

import sqlite3

import pytest

from backend.application.inventory.use_cases import (
    PostInventoryMovementUseCase,
    ReverseInventoryMovementUseCase,
)
from backend.application.inventory.use_cases.rebuild_inventory_balances import (
    RebuildInventoryBalancesUseCase,
    ValidateInventoryProjectionUseCase,
)
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.enums import MovementType
from backend.infrastructure.db.repositories.inventory.unit_of_work import (
    InventoryUnitOfWork,
)
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_inventory_schema(c)
    c.commit()
    yield c
    c.close()


def _receipt(conn, op, qty="10"):
    line = InventoryMovementLine.create(product_id="p1", quantity=Decimal(qty),
                                        to_location_id="loc1")
    mv = InventoryMovement.create(
        movement_type=MovementType.PURCHASE_RECEIPT, branch_id="b1", warehouse_id="w1",
        source_module="procurement", source_document_type="GR", source_document_id="gr1",
        operation_id=op, created_by_user_id="u1", lines=[line])
    PostInventoryMovementUseCase().execute(conn, mv, actor_user_id="u1")


def _issue(conn, op, qty="4"):
    line = InventoryMovementLine.create(product_id="p1", quantity=Decimal(qty),
                                        from_location_id="loc1")
    mv = InventoryMovement.create(
        movement_type=MovementType.SALE_ISSUE, branch_id="b1", warehouse_id="w1",
        source_module="sales", source_document_type="SALE", source_document_id="s1",
        operation_id=op, created_by_user_id="u1", lines=[line])
    PostInventoryMovementUseCase().execute(conn, mv, actor_user_id="u1")


def test_rebuild_matches_live_projection_zero_drift(conn):
    _receipt(conn, "op-1", "10")
    _issue(conn, "op-2", "4")
    rebuilt = RebuildInventoryBalancesUseCase().rebuild(conn)
    # net physical = 6 on the AVAILABLE/loc1 bucket
    (only,) = list(rebuilt.values())
    assert only.quantity == Decimal("6")
    assert ValidateInventoryProjectionUseCase(conn).validate() == []
    assert ValidateInventoryProjectionUseCase(conn).has_drift() is False


def test_rebuild_accounts_for_reversal(conn):
    _receipt(conn, "op-1", "10")
    _issue(conn, "op-2", "4")
    with InventoryUnitOfWork(conn) as uow:
        issue_id = uow.ledger.find_by_operation_id("op-2")["id"]
    ReverseInventoryMovementUseCase().execute(
        conn, movement_id=issue_id, operation_id="rev-1", actor_user_id="u1",
        reason="x")
    rebuilt = RebuildInventoryBalancesUseCase().rebuild(conn)
    (only,) = list(rebuilt.values())
    assert only.quantity == Decimal("10")  # issue undone
    assert ValidateInventoryProjectionUseCase(conn).has_drift() is False


def test_validator_detects_corrupted_balance(conn):
    _receipt(conn, "op-1", "10")
    # Corrupt the live projection out of band.
    conn.execute("UPDATE inventory_balances SET quantity='999'")
    conn.commit()
    drifts = ValidateInventoryProjectionUseCase(conn).validate()
    assert len(drifts) == 1
    d = drifts[0]
    assert d.projected_quantity == Decimal("999")
    assert d.rebuilt_quantity == Decimal("10")
    assert d.quantity_drift == Decimal("989")


def test_rebuild_does_not_mutate_ledger_or_balances(conn):
    _receipt(conn, "op-1", "10")
    before_ledger = conn.execute("SELECT COUNT(*) FROM inventory_ledger").fetchone()[0]
    before_bal = conn.execute(
        "SELECT quantity FROM inventory_balances").fetchone()[0]
    RebuildInventoryBalancesUseCase().rebuild(conn)
    after_ledger = conn.execute("SELECT COUNT(*) FROM inventory_ledger").fetchone()[0]
    after_bal = conn.execute("SELECT quantity FROM inventory_balances").fetchone()[0]
    assert before_ledger == after_ledger and before_bal == after_bal
