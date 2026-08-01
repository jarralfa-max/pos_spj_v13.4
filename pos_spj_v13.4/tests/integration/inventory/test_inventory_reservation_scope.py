"""P0-A slice 6 (§5.3) — branch/warehouse scope enforced on reservations.

Create/Release/Allocate validate the target branch/warehouse against the actor's
InventoryExecutionContext. Out-of-scope → SCOPE_DENIED; availability is untouched
and the reservation is not created/released. UI ids are never trusted blindly.
"""

from decimal import Decimal

import sqlite3

import pytest

from backend.application.inventory.execution_context import InventoryExecutionContext
from backend.application.inventory.permissions import InventoryPermissions
from backend.application.inventory.use_cases import (
    AllocateReservationUseCase,
    CreateReservationUseCase,
    PostInventoryMovementUseCase,
    ReleaseReservationUseCase,
)
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.enums import (
    InventoryStatus,
    MovementType,
    ReservationSource,
)
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


def _reserve(conn, *, op="op-1", context=None):
    return CreateReservationUseCase().execute(
        conn, product_id="p1", branch_id="b1", warehouse_id="w1",
        source=ReservationSource.SALE, source_document_id="s1", quantity=Decimal("4"),
        operation_id=op, actor_user_id="u1", location_id="loc1", context=context)


def _available(conn):
    with InventoryUnitOfWork(conn) as uow:
        bal = uow.balances.get(product_id="p1", branch_id="b1", warehouse_id="w1",
                               inventory_status=InventoryStatus.AVAILABLE,
                               location_id="loc1")
        return bal.available_quantity if bal else Decimal("0")


def test_create_in_scope_reserves(conn):
    _receipt(conn)
    assert _reserve(conn, context=_ctx()).success and _available(conn) == Decimal("6")


def test_create_out_of_branch_scope_denied_untouched(conn):
    _receipt(conn)
    res = _reserve(conn, context=_ctx(branch="b2"))
    assert not res.success and res.error_code == "SCOPE_DENIED"
    assert _available(conn) == Decimal("10")  # availability untouched


def test_create_out_of_warehouse_scope_denied(conn):
    _receipt(conn)
    res = _reserve(conn, context=_ctx(warehouses=("w9",)))
    assert not res.success and res.error_code == "SCOPE_DENIED"
    assert _available(conn) == Decimal("10")


def test_create_no_context_backward_compatible(conn):
    _receipt(conn)
    assert _reserve(conn).success and _available(conn) == Decimal("6")


def test_release_enforces_scope_of_reservation(conn):
    _receipt(conn)
    res = _reserve(conn)
    denied = ReleaseReservationUseCase().execute(
        conn, reservation_id=res.entity_id, operation_id="rel-1", actor_user_id="u1",
        context=_ctx(branch="b2"))
    assert not denied.success and denied.error_code == "SCOPE_DENIED"
    assert _available(conn) == Decimal("6")  # still reserved


def test_allocate_enforces_scope_of_reservation(conn):
    _receipt(conn)
    res = _reserve(conn)
    denied = AllocateReservationUseCase().execute(
        conn, reservation_id=res.entity_id, operation_id="al-1", actor_user_id="u1",
        context=_ctx(warehouses=("w9",)))
    assert not denied.success and denied.error_code == "SCOPE_DENIED"
