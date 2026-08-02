"""P0-C (§9.1) — lot quality changes move stock between physical buckets.

Blocking a lot is not just metadata: it posts a state-transfer movement that moves
the lot's stock AVAILABLE → QUALITY_BLOCKED (and back on release), so availability
excludes a blocked lot and restores it on release. Atomic within one UoW.
"""

from decimal import Decimal

import sqlite3

import pytest

from backend.application.inventory.queries import InventoryAvailabilityQueryService
from backend.application.inventory.use_cases import (
    PostInventoryMovementUseCase,
    RegisterInventoryLotUseCase,
)
from backend.application.inventory.use_cases.lot_use_cases import (
    SetLotQualityStatusUseCase,
)
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.enums import (
    InventoryStatus,
    LotOrigin,
    LotQualityStatus,
    MovementType,
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


def _lot_with_stock(conn, qty="10"):
    reg = RegisterInventoryLotUseCase().execute(
        conn, product_id="p1", lot_code="L-1", origin_type=LotOrigin.PURCHASE,
        operation_id="lot-1", actor_user_id="u1", branch_id="b1")
    lot_id = reg.entity_id
    line = InventoryMovementLine.create(product_id="p1", quantity=Decimal(qty),
                                        to_location_id="loc1", lot_id=lot_id)
    mv = InventoryMovement.create(
        movement_type=MovementType.PURCHASE_RECEIPT, branch_id="b1", warehouse_id="w1",
        source_module="procurement", source_document_type="GR", source_document_id="gr1",
        operation_id="rcv-1", created_by_user_id="u1", lines=[line])
    PostInventoryMovementUseCase().execute(conn, mv, actor_user_id="u1")
    return lot_id


def _available(conn):
    return InventoryAvailabilityQueryService(conn).get_availability(
        product_id="p1", branch_id="b1").available


def _bucket(conn, status):
    with InventoryUnitOfWork(conn) as uow:
        bal = uow.balances.get(product_id="p1", branch_id="b1", warehouse_id="w1",
                               inventory_status=status, location_id="loc1",
                               lot_id=_LOT[0])
        return bal.quantity if bal else Decimal("0")


_LOT = [None]


def test_blocking_lot_removes_it_from_availability(conn):
    _LOT[0] = _lot_with_stock(conn, "10")
    assert _available(conn) == Decimal("10")
    res = SetLotQualityStatusUseCase().execute(
        conn, lot_id=_LOT[0], new_status=LotQualityStatus.BLOCKED,
        operation_id="blk-1", actor_user_id="qa", reason="daño")
    assert res.success
    assert _available(conn) == Decimal("0")                          # excluido
    assert _bucket(conn, InventoryStatus.QUALITY_BLOCKED) == Decimal("10")  # movido


def test_releasing_lot_restores_availability(conn):
    _LOT[0] = _lot_with_stock(conn, "10")
    SetLotQualityStatusUseCase().execute(
        conn, lot_id=_LOT[0], new_status=LotQualityStatus.BLOCKED,
        operation_id="blk-1", actor_user_id="qa", reason="daño")
    assert _available(conn) == Decimal("0")
    res = SetLotQualityStatusUseCase().execute(
        conn, lot_id=_LOT[0], new_status=LotQualityStatus.RELEASED,
        operation_id="rel-1", actor_user_id="qa", reason="ok")
    assert res.success
    assert _available(conn) == Decimal("10")                       # restaurado
    assert _bucket(conn, InventoryStatus.QUALITY_BLOCKED) == Decimal("0")


def test_quarantining_lot_moves_to_quarantine_bucket(conn):
    _LOT[0] = _lot_with_stock(conn, "6")
    SetLotQualityStatusUseCase().execute(
        conn, lot_id=_LOT[0], new_status=LotQualityStatus.QUARANTINED,
        operation_id="q-1", actor_user_id="qa", reason="revisión")
    assert _available(conn) == Decimal("0")
    assert _bucket(conn, InventoryStatus.QUARANTINED) == Decimal("6")


def test_lot_quality_change_persists_status(conn):
    _LOT[0] = _lot_with_stock(conn, "5")
    SetLotQualityStatusUseCase().execute(
        conn, lot_id=_LOT[0], new_status=LotQualityStatus.BLOCKED,
        operation_id="blk-1", actor_user_id="qa")
    with InventoryUnitOfWork(conn) as uow:
        lot = uow.lots.get(_LOT[0])
    assert lot.quality_status is LotQualityStatus.BLOCKED
