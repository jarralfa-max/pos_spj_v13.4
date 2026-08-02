"""§4.1/§19.3 — inventory domain identity is a REAL UUIDv7 at runtime.

Not a code-pattern check: it builds actual entities and persists a movement, then
asserts every generated id validates as a canonical lowercase UUIDv7 (version 7).
"""

from decimal import Decimal

import sqlite3

import pytest

from backend.application.inventory.use_cases import PostInventoryMovementUseCase
from backend.domain.inventory.entities.inventory_lot import InventoryLot
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.enums import LotOrigin, MovementType
from backend.infrastructure.db.repositories.inventory.unit_of_work import (
    InventoryUnitOfWork,
)
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from backend.shared.ids import validate_uuidv7


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_inventory_schema(c)
    c.commit()
    yield c
    c.close()


def test_movement_and_line_ids_are_uuidv7():
    line = InventoryMovementLine.create(product_id="p1", quantity=Decimal("1"),
                                        to_location_id="loc1")
    mv = InventoryMovement.create(
        movement_type=MovementType.PURCHASE_RECEIPT, branch_id="b1", warehouse_id="w1",
        source_module="procurement", source_document_type="GR", source_document_id="gr1",
        operation_id="op-1", created_by_user_id="u1", lines=[line])
    validate_uuidv7(mv.id)
    validate_uuidv7(line.id)


def test_lot_id_is_uuidv7():
    lot = InventoryLot.create(product_id="p1", lot_code="L-1",
                              origin_type=LotOrigin.PURCHASE)
    validate_uuidv7(lot.id)


def test_persisted_ledger_id_is_uuidv7(conn):
    line = InventoryMovementLine.create(product_id="p1", quantity=Decimal("5"),
                                        to_location_id="loc1")
    mv = InventoryMovement.create(
        movement_type=MovementType.PURCHASE_RECEIPT, branch_id="b1", warehouse_id="w1",
        source_module="procurement", source_document_type="GR", source_document_id="gr1",
        operation_id="op-1", created_by_user_id="u1", lines=[line])
    PostInventoryMovementUseCase().execute(conn, mv, actor_user_id="u1")
    with InventoryUnitOfWork(conn) as uow:
        row = uow.ledger.find_by_operation_id("op-1")
    validate_uuidv7(row["id"])
