"""P0-B (§4.3) — canonical unit_id (UUIDv7) on ledger lines.

The movement line carries a canonical `unit_id` (a units_of_measure UUID) alongside
the legacy free-text `unit`. When provided it must be a real UUIDv7 and it must
round-trip through the ledger. `None` is allowed during the transition.
"""

from decimal import Decimal

import sqlite3

import pytest

from backend.application.inventory.use_cases import PostInventoryMovementUseCase
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.enums import MovementType
from backend.infrastructure.db.repositories.inventory.unit_of_work import (
    InventoryUnitOfWork,
)
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from backend.shared.ids import new_uuid


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_inventory_schema(c)
    c.commit()
    yield c
    c.close()


def _movement(line, op="op-1"):
    return InventoryMovement.create(
        movement_type=MovementType.PURCHASE_RECEIPT, branch_id="b1", warehouse_id="w1",
        source_module="procurement", source_document_type="GR", source_document_id="gr1",
        operation_id=op, created_by_user_id="u1", lines=[line])


def test_line_accepts_canonical_unit_id():
    unit_id = new_uuid()
    line = InventoryMovementLine.create(
        product_id="p1", quantity=Decimal("1"), to_location_id="loc1", unit_id=unit_id)
    assert line.unit_id == unit_id


def test_line_rejects_non_uuidv7_unit_id():
    with pytest.raises(ValueError):
        InventoryMovementLine.create(
            product_id="p1", quantity=Decimal("1"), to_location_id="loc1",
            unit_id="KG")  # free-text unit is not a canonical id


def test_unit_id_is_optional_during_transition():
    line = InventoryMovementLine.create(
        product_id="p1", quantity=Decimal("1"), to_location_id="loc1")
    assert line.unit_id is None


def test_unit_id_round_trips_through_ledger(conn):
    unit_id = new_uuid()
    line = InventoryMovementLine.create(
        product_id="p1", quantity=Decimal("5"), to_location_id="loc1", unit_id=unit_id)
    PostInventoryMovementUseCase().execute(conn, _movement(line), actor_user_id="u1")
    with InventoryUnitOfWork(conn) as uow:
        mv_id = uow.ledger.find_by_operation_id("op-1")["id"]
        rows = uow.ledger.get_lines(mv_id)
    assert rows[0]["unit_id"] == unit_id


def test_schema_has_unit_id_column(conn):
    cols = [r[1] for r in conn.execute("PRAGMA table_info(inventory_ledger_lines)")]
    assert "unit_id" in cols
