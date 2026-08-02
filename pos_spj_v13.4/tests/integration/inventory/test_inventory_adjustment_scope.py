"""P0-A slice 5 (§5.3) — branch/warehouse scope enforced on adjustments.

Create/Approve/Post adjustment validate the target branch/warehouse against the
actor's InventoryExecutionContext. Out-of-scope → SCOPE_DENIED and no adjustment is
created / posted; the branch/warehouse ids from the UI are never trusted blindly.
"""

from decimal import Decimal

import sqlite3

import pytest

from backend.application.inventory.execution_context import InventoryExecutionContext
from backend.application.inventory.permissions import InventoryPermissions
from backend.application.inventory.use_cases import (
    ApproveAdjustmentUseCase,
    CreateAdjustmentUseCase,
    PostAdjustmentUseCase,
    PostInventoryMovementUseCase,
)
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.enums import AdjustmentReason, MovementType
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_inventory_schema(c)
    c.commit()
    yield c
    c.close()


def _seed(conn, qty="10"):
    line = InventoryMovementLine.create(product_id="p1", quantity=Decimal(qty),
                                        to_location_id="loc1")
    mv = InventoryMovement.create(
        movement_type=MovementType.PURCHASE_RECEIPT, branch_id="b1", warehouse_id="w1",
        source_module="procurement", source_document_type="GR", source_document_id="gr1",
        operation_id="seed", created_by_user_id="u1", lines=[line])
    PostInventoryMovementUseCase().execute(conn, mv, actor_user_id="u1")


def _ctx(*, branch="b1", warehouses=("w1",),
         perms=(InventoryPermissions.VIEW_OWN_BRANCH,)):
    return InventoryExecutionContext(
        actor_user_id="clerk", active_branch_id=branch,
        allowed_warehouse_ids=frozenset(warehouses), permissions=frozenset(perms))


def _create(conn, *, context=None, op="adj-1"):
    return CreateAdjustmentUseCase().execute(
        conn, folio="ADJ-1", branch_id="b1", warehouse_id="w1",
        reason=AdjustmentReason.DAMAGE,
        lines=[{"product_id": "p1", "quantity_delta": Decimal("-1"),
                "location_id": "loc1"}],
        operation_id=op, actor_user_id="clerk", context=context)


def test_create_in_scope_succeeds(conn):
    _seed(conn)
    res = _create(conn, context=_ctx())
    assert res.success


def test_create_out_of_branch_scope_denied(conn):
    _seed(conn)
    res = _create(conn, context=_ctx(branch="b2"))
    assert not res.success and res.error_code == "SCOPE_DENIED"


def test_create_out_of_warehouse_scope_denied(conn):
    _seed(conn)
    res = _create(conn, context=_ctx(warehouses=("w9",)))
    assert not res.success and res.error_code == "SCOPE_DENIED"


def test_create_no_context_backward_compatible(conn):
    _seed(conn)
    assert _create(conn).success


def test_approve_and_post_enforce_scope(conn):
    _seed(conn, "100")
    # large negative delta → requires approval
    res = CreateAdjustmentUseCase().execute(
        conn, folio="ADJ-2", branch_id="b1", warehouse_id="w1",
        reason=AdjustmentReason.DAMAGE,
        lines=[{"product_id": "p1", "quantity_delta": Decimal("-90"),
                "location_id": "loc1"}],
        operation_id="adj-2", actor_user_id="clerk")
    adj_id = res.entity_id
    # approve from another branch scope → denied
    denied = ApproveAdjustmentUseCase().execute(
        conn, adjustment_id=adj_id, operation_id="ap-1", actor_user_id="boss",
        context=_ctx(branch="b2"))
    assert not denied.success and denied.error_code == "SCOPE_DENIED"
    # approve in-scope → ok
    ok = ApproveAdjustmentUseCase().execute(
        conn, adjustment_id=adj_id, operation_id="ap-2", actor_user_id="boss",
        context=_ctx(branch="b1"))
    assert ok.success
    # post out-of-scope → denied
    pd = PostAdjustmentUseCase().execute(
        conn, adjustment_id=adj_id, operation_id="po-1", actor_user_id="clerk",
        context=_ctx(warehouses=("w9",)))
    assert not pd.success and pd.error_code == "SCOPE_DENIED"
