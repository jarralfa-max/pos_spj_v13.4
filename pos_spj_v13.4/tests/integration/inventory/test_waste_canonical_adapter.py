"""INV-27 corte — merma descuenta stock por el ledger canónico (WASTE).

WasteApplicationService, con el CanonicalWasteInventoryService inyectado (como en
modulos/merma.py), postea un movimiento WASTE al ledger en vez de mutar
inventory_stock. El movimiento y la fila de merma son atómicos e idempotentes.
"""

from decimal import Decimal

import sqlite3

import pytest

from backend.application.commands.waste_commands import RegisterWasteCommand
from backend.application.services.waste_application_service import WasteApplicationService
from backend.application.inventory.queries import InventoryAvailabilityQueryService
from backend.application.inventory.use_cases import PostInventoryMovementUseCase
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement, InventoryMovementLine)
from backend.domain.inventory.enums import MovementType
from backend.infrastructure.db.repositories.waste_repository import WasteRepository
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from core.services.inventory.canonical_waste_adapter import CanonicalWasteInventoryService

PRODUCT = "01900000-0000-7000-8000-000000000001"
BRANCH = "01900000-0000-7000-8000-000000000011"


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_inventory_schema(c)
    c.execute("""CREATE TABLE productos (id TEXT PRIMARY KEY, nombre TEXT, precio_compra REAL,
                 costo REAL, precio_costo REAL, costo_unitario REAL, unidad TEXT,
                 existencia REAL, activo INTEGER)""")
    c.execute("""CREATE TABLE mermas (id TEXT PRIMARY KEY, producto_id TEXT NOT NULL,
                 sucursal_id TEXT NOT NULL, cantidad REAL NOT NULL, unidad TEXT, motivo TEXT,
                 costo_unitario REAL, valor_perdida REAL, notas TEXT, usuario TEXT,
                 operation_id TEXT, created_at TEXT, fecha TEXT)""")
    c.execute("INSERT INTO productos(id,nombre,precio_compra,unidad,existencia,activo)"
              " VALUES (?, 'Arrachera', 125.5, 'kg', 10, 1)", (PRODUCT,))
    # seed canonical stock: 10 available at location = branch
    line = InventoryMovementLine.create(product_id=PRODUCT, quantity=Decimal("10"),
                                        to_location_id=BRANCH, reason_code="OPENING")
    mv = InventoryMovement.create(
        movement_type=MovementType.ADJUSTMENT_IN, branch_id=BRANCH, warehouse_id=BRANCH,
        source_module="t", source_document_type="SEED", source_document_id="s",
        operation_id="seed", created_by_user_id="s", lines=[line])
    PostInventoryMovementUseCase().execute(c, mv, actor_user_id="s")
    c.commit()
    yield c
    c.close()


def _service(conn):
    return WasteApplicationService(
        repository=WasteRepository(conn),
        inventory_service=CanonicalWasteInventoryService(lambda: conn))


def _cmd(op="w1", qty=3.0):
    return RegisterWasteCommand(
        operation_id=op, branch_id=BRANCH, user_id="u1", user_name="cajero",
        payload={}, product_id=PRODUCT, quantity=qty, reason="Deterioro",
        notes="", date=None, unit="kg")


def _available(conn):
    return InventoryAvailabilityQueryService(conn).get_availability(
        product_id=PRODUCT, branch_id=BRANCH).available


def test_waste_decrements_canonical_ledger(conn):
    result = _service(conn).register(_cmd(qty=3.0))
    assert result.success, result.message
    assert _available(conn) == Decimal("7")   # 10 − 3
    row = conn.execute("SELECT movement_type FROM inventory_ledger"
                       " WHERE operation_id='w1'").fetchone()
    assert row["movement_type"] == "WASTE"


def test_waste_is_idempotent(conn):
    _service(conn).register(_cmd(op="w1", qty=3.0))
    # a replay of the same operation_id is rejected by the waste repo dedupe
    second = _service(conn).register(_cmd(op="w1", qty=3.0))
    assert not second.success
    assert _available(conn) == Decimal("7")  # deducted once


def test_waste_beyond_stock_fails_and_rolls_back(conn):
    result = _service(conn).register(_cmd(qty=99.0))
    assert not result.success
    assert _available(conn) == Decimal("10")  # unchanged
    assert conn.execute("SELECT COUNT(*) FROM mermas").fetchone()[0] == 0
