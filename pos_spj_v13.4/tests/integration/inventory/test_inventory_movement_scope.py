"""P0-A slice 4 (§5.3) — branch/warehouse scope enforced on the stock write path.

Post/Reverse movement validate the movement's real branch and warehouse against the
actor's resolved InventoryExecutionContext. Out-of-scope operations fail closed
(SCOPE_DENIED) and never touch the balance; the ids on the movement are not trusted.
"""

from decimal import Decimal

import sqlite3

import pytest

from backend.application.inventory.execution_context import InventoryExecutionContext
from backend.application.inventory.permissions import InventoryPermissions
from backend.application.inventory.use_cases import (
    PostInventoryMovementUseCase,
    ReverseInventoryMovementUseCase,
)
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.enums import InventoryStatus, MovementType
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


def _receipt(op, qty="10"):
    line = InventoryMovementLine.create(
        product_id="p1", quantity=Decimal(qty), to_location_id="loc1")
    return InventoryMovement.create(
        movement_type=MovementType.PURCHASE_RECEIPT, branch_id="b1", warehouse_id="w1",
        source_module="procurement", source_document_type="GOODS_RECEIPT",
        source_document_id="gr1", operation_id=op, created_by_user_id="u1", lines=[line])


def _ctx(*, branch="b1", warehouses=("w1",), perms=(InventoryPermissions.VIEW_OWN_BRANCH,)):
    return InventoryExecutionContext(
        actor_user_id="u1", active_branch_id=branch,
        allowed_warehouse_ids=frozenset(warehouses),
        permissions=frozenset(perms))


def _balance(conn):
    with InventoryUnitOfWork(conn) as uow:
        bal = uow.balances.get(product_id="p1", branch_id="b1", warehouse_id="w1",
                               inventory_status=InventoryStatus.AVAILABLE,
                               location_id="loc1")
        return bal.quantity if bal else Decimal("0")


def test_in_scope_context_allows_post(conn):
    res = PostInventoryMovementUseCase().execute(
        conn, _receipt("op-1"), actor_user_id="u1", context=_ctx())
    assert res.success and _balance(conn) == Decimal("10")


def test_out_of_branch_scope_denies_and_does_not_touch_balance(conn):
    # actor's own branch is b2; the movement targets b1 → denied.
    res = PostInventoryMovementUseCase().execute(
        conn, _receipt("op-1"), actor_user_id="u1", context=_ctx(branch="b2"))
    assert not res.success and res.error_code == "SCOPE_DENIED"
    assert _balance(conn) == Decimal("0")


def test_out_of_warehouse_scope_denies(conn):
    res = PostInventoryMovementUseCase().execute(
        conn, _receipt("op-1"), actor_user_id="u1", context=_ctx(warehouses=("w9",)))
    assert not res.success and res.error_code == "SCOPE_DENIED"
    assert _balance(conn) == Decimal("0")


def test_global_scope_bypasses_warehouse_allowlist(conn):
    res = PostInventoryMovementUseCase().execute(
        conn, _receipt("op-1"), actor_user_id="u1",
        context=_ctx(warehouses=(), perms=(InventoryPermissions.VIEW_ALL_BRANCHES,)))
    assert res.success and _balance(conn) == Decimal("10")


def test_no_context_keeps_backward_compatible_behavior(conn):
    res = PostInventoryMovementUseCase().execute(
        conn, _receipt("op-1"), actor_user_id="u1")
    assert res.success and _balance(conn) == Decimal("10")


def test_reverse_enforces_scope_of_original(conn):
    PostInventoryMovementUseCase().execute(conn, _receipt("op-1"), actor_user_id="u1")
    with InventoryUnitOfWork(conn) as uow:
        mv_id = uow.ledger.find_by_operation_id("op-1")["id"]
    res = ReverseInventoryMovementUseCase().execute(
        conn, movement_id=mv_id, operation_id="rev-1", actor_user_id="u1",
        reason="x", context=_ctx(branch="b2"))
    assert not res.success and res.error_code == "SCOPE_DENIED"
    assert _balance(conn) == Decimal("10")  # not reversed
