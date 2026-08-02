"""P0-A slice 7 (§5.3) — branch/warehouse scope enforced on quarantine & counts.

Quarantine (create/release/dispose) and count (create/record/confirm/approve)
validate branch/warehouse against the actor's InventoryExecutionContext: from the
UI args on create, from the fetched entity thereafter. Out-of-scope → SCOPE_DENIED.
"""

from decimal import Decimal

import sqlite3

import pytest

from backend.application.inventory.execution_context import InventoryExecutionContext
from backend.application.inventory.permissions import InventoryPermissions
from backend.application.inventory.use_cases import (
    ApproveCountUseCase,
    ConfirmCountUseCase,
    CreateCountUseCase,
    DisposeQuarantineUseCase,
    PostInventoryMovementUseCase,
    QuarantineStockUseCase,
    ReleaseQuarantineUseCase,
)
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.enums import (
    CountType,
    MovementType,
    QuarantineReason,
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


def _receipt(conn, qty="10"):
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
        actor_user_id="u1", active_branch_id=branch,
        allowed_warehouse_ids=frozenset(warehouses), permissions=frozenset(perms))


# ── quarantine ───────────────────────────────────────────────────────────────
def _quarantine(conn, *, op="q1", context=None):
    return QuarantineStockUseCase().execute(
        conn, product_id="p1", branch_id="b1", warehouse_id="w1",
        reason=QuarantineReason.QUALITY_FAILURE, quantity=Decimal("3"), operation_id=op,
        actor_user_id="u1", location_id="loc1", context=context)


def test_quarantine_create_in_scope(conn):
    _receipt(conn)
    assert _quarantine(conn, context=_ctx()).success


def test_quarantine_create_out_of_scope_denied(conn):
    _receipt(conn)
    res = _quarantine(conn, context=_ctx(branch="b2"))
    assert not res.success and res.error_code == "SCOPE_DENIED"


def test_quarantine_release_enforces_scope(conn):
    _receipt(conn)
    q = _quarantine(conn)
    denied = ReleaseQuarantineUseCase().execute(
        conn, quarantine_id=q.entity_id, operation_id="rel-1", actor_user_id="qa",
        context=_ctx(warehouses=("w9",)))
    assert not denied.success and denied.error_code == "SCOPE_DENIED"


def test_quarantine_dispose_enforces_scope(conn):
    _receipt(conn)
    q = _quarantine(conn)
    denied = DisposeQuarantineUseCase().execute(
        conn, quarantine_id=q.entity_id, operation_id="dis-1", actor_user_id="qa",
        context=_ctx(branch="b2"))
    assert not denied.success and denied.error_code == "SCOPE_DENIED"


# ── counts ───────────────────────────────────────────────────────────────────
def _create_count(conn, *, op="c1", context=None):
    return CreateCountUseCase().execute(
        conn, folio="CNT-1", count_type=CountType.CYCLE_COUNT, branch_id="b1",
        warehouse_id="w1", scope_lines=[{"product_id": "p1", "location_id": "loc1"}],
        operation_id=op, actor_user_id="u1", context=context)


def test_count_create_in_scope(conn):
    _receipt(conn)
    assert _create_count(conn, context=_ctx()).success


def test_count_create_out_of_scope_denied(conn):
    _receipt(conn)
    res = _create_count(conn, context=_ctx(warehouses=("w9",)))
    assert not res.success and res.error_code == "SCOPE_DENIED"


def test_count_confirm_and_approve_enforce_scope(conn):
    _receipt(conn)
    c = _create_count(conn)
    denied = ConfirmCountUseCase().execute(
        conn, count_id=c.entity_id, operation_id="cf-1", actor_user_id="u1",
        context=_ctx(branch="b2"))
    assert not denied.success and denied.error_code == "SCOPE_DENIED"
    denied2 = ApproveCountUseCase().execute(
        conn, count_id=c.entity_id, operation_id="ap-1", actor_user_id="boss",
        context=_ctx(warehouses=("w9",)))
    assert not denied2.success and denied2.error_code == "SCOPE_DENIED"


def test_count_create_no_context_backward_compatible(conn):
    _receipt(conn)
    assert _create_count(conn).success
