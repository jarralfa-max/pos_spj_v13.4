"""INV-27 corte — explosión de receta en compra al ledger canónico.

Comprar un producto con receta consume sus componentes vía ADJUSTMENT_OUT
canónico (no movimientos_inventario legacy), idempotente por operation_id.
"""

from decimal import Decimal

import sqlite3

import pytest

from backend.application.event_handlers.inventory.purchase_recipe_explosion_bridge import (
    CanonicalPurchaseRecipeExplosionHandler,
)
from backend.application.inventory.queries import InventoryAvailabilityQueryService
from backend.application.inventory.use_cases import PostInventoryMovementUseCase
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement, InventoryMovementLine)
from backend.domain.inventory.enums import MovementType
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_inventory_schema(c)
    # legacy recipe tables (read-only by the handler)
    c.execute("CREATE TABLE product_recipes (id TEXT PRIMARY KEY, base_product_id TEXT,"
              " is_active INT DEFAULT 1)")
    c.execute("CREATE TABLE product_recipe_components (id TEXT PRIMARY KEY, recipe_id TEXT,"
              " component_product_id TEXT, cantidad REAL)")
    c.execute("INSERT INTO product_recipes VALUES ('r1','marinado',1)")
    c.execute("INSERT INTO product_recipe_components VALUES ('c1','r1','pollo',2),"
              " ('c2','r1','marinada',1)")
    c.commit()
    yield c
    c.close()


def _seed(conn, product_id, qty, branch="b1"):
    line = InventoryMovementLine.create(product_id=product_id, quantity=Decimal(qty),
                                        to_location_id=branch, reason_code="OPENING")
    mv = InventoryMovement.create(
        movement_type=MovementType.ADJUSTMENT_IN, branch_id=branch, warehouse_id=branch,
        source_module="t", source_document_type="SEED", source_document_id="s",
        operation_id=f"seed:{product_id}", created_by_user_id="s", lines=[line])
    PostInventoryMovementUseCase().execute(conn, mv, actor_user_id="s")


def _avail(conn, product_id, branch="b1"):
    return InventoryAvailabilityQueryService(conn).get_availability(
        product_id=product_id, branch_id=branch).available


def _payload(qty="3", event_id="gr-1"):
    return {"event_id": event_id, "warehouse_id": "b1", "user_id": "u1",
            "lines": [{"product_id": "marinado", "quantity": qty}]}


def test_explosion_consumes_components_canonically(conn):
    _seed(conn, "pollo", "20")
    _seed(conn, "marinada", "20")
    CanonicalPurchaseRecipeExplosionHandler(conn).handle(_payload(qty="3"))
    assert _avail(conn, "pollo") == Decimal("14")      # 20 − 2*3
    assert _avail(conn, "marinada") == Decimal("17")   # 20 − 1*3
    assert conn.execute("SELECT COUNT(*) FROM inventory_ledger"
                        " WHERE operation_id='gr-1:marinado:recipe'").fetchone()[0] == 1


def test_explosion_idempotent(conn):
    _seed(conn, "pollo", "20")
    _seed(conn, "marinada", "20")
    CanonicalPurchaseRecipeExplosionHandler(conn).handle(_payload(event_id="gr-1"))
    CanonicalPurchaseRecipeExplosionHandler(conn).handle(_payload(event_id="gr-1"))
    assert _avail(conn, "pollo") == Decimal("14")  # consumed once


def test_no_recipe_is_noop(conn):
    payload = _payload()
    payload["lines"][0]["product_id"] = "sinreceta"
    CanonicalPurchaseRecipeExplosionHandler(conn).handle(payload)
    assert conn.execute("SELECT COUNT(*) FROM inventory_ledger").fetchone()[0] == 0
