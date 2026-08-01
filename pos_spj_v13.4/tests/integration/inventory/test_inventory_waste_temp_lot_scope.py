"""P0-A slice 8 (§5.3) — scope enforced on waste, cold-chain and lots.

Waste (branch+warehouse from UI), temperature (warehouse-only), and lot register /
quality-status (branch) validate against the actor's InventoryExecutionContext.
Out-of-scope → SCOPE_DENIED.
"""

from decimal import Decimal

import sqlite3

import pytest

from backend.application.inventory.execution_context import InventoryExecutionContext
from backend.application.inventory.permissions import InventoryPermissions
from backend.application.inventory.use_cases import (
    PostInventoryMovementUseCase,
    RecordTemperatureReadingUseCase,
    RegisterInventoryLotUseCase,
    RegisterWasteUseCase,
)
from backend.application.inventory.use_cases.lot_use_cases import (
    SetLotQualityStatusUseCase,
)
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.enums import (
    LotOrigin,
    LotQualityStatus,
    MovementType,
    TemperaturePoint,
    WasteType,
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


# ── waste ────────────────────────────────────────────────────────────────────
def _waste(conn, *, op="wst-1", context=None):
    return RegisterWasteUseCase().execute(
        conn, product_id="p1", branch_id="b1", warehouse_id="w1",
        waste_type=WasteType.DAMAGE, quantity=Decimal("1"), operation_id=op,
        actor_user_id="u1", location_id="loc1", context=context)


def test_waste_in_scope(conn):
    _receipt(conn)
    assert _waste(conn, context=_ctx()).success


def test_waste_out_of_branch_scope_denied(conn):
    _receipt(conn)
    res = _waste(conn, context=_ctx(branch="b2"))
    assert not res.success and res.error_code == "SCOPE_DENIED"


def test_waste_out_of_warehouse_scope_denied(conn):
    _receipt(conn)
    res = _waste(conn, context=_ctx(warehouses=("w9",)))
    assert not res.success and res.error_code == "SCOPE_DENIED"


def test_waste_no_context_backward_compatible(conn):
    _receipt(conn)
    assert _waste(conn).success


# ── temperature (warehouse-only) ─────────────────────────────────────────────
def _temp(conn, *, context=None):
    return RecordTemperatureReadingUseCase().execute(
        conn, sensor_id="s1", warehouse_id="w1", temperature=Decimal("4"),
        reading_point=TemperaturePoint.STORAGE, min_temp=Decimal("0"),
        max_temp=Decimal("8"), operation_id="t1", actor_user_id="u1", context=context)


def test_temperature_in_scope(conn):
    assert _temp(conn, context=_ctx()).success


def test_temperature_out_of_warehouse_scope_denied(conn):
    res = _temp(conn, context=_ctx(warehouses=("w9",)))
    assert not res.success and res.error_code == "SCOPE_DENIED"


# ── lots (branch) ────────────────────────────────────────────────────────────
def test_lot_register_out_of_branch_scope_denied(conn):
    res = RegisterInventoryLotUseCase().execute(
        conn, product_id="p1", lot_code="L-1", origin_type=LotOrigin.PURCHASE,
        operation_id="lot-1", actor_user_id="u1", branch_id="b1",
        context=_ctx(branch="b2"))
    assert not res.success and res.error_code == "SCOPE_DENIED"


def test_lot_register_in_scope(conn):
    res = RegisterInventoryLotUseCase().execute(
        conn, product_id="p1", lot_code="L-1", origin_type=LotOrigin.PURCHASE,
        operation_id="lot-1", actor_user_id="u1", branch_id="b1", context=_ctx())
    assert res.success


def test_lot_quality_status_enforces_branch_scope(conn):
    reg = RegisterInventoryLotUseCase().execute(
        conn, product_id="p1", lot_code="L-1", origin_type=LotOrigin.PURCHASE,
        operation_id="lot-1", actor_user_id="u1", branch_id="b1")
    denied = SetLotQualityStatusUseCase().execute(
        conn, lot_id=reg.entity_id, new_status=LotQualityStatus.QUARANTINED,
        operation_id="q-1", actor_user_id="qa", context=_ctx(branch="b2"))
    assert not denied.success and denied.error_code == "SCOPE_DENIED"
