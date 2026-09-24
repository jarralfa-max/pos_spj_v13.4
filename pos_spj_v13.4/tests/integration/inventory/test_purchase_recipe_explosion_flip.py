"""INV-27 corte — explosión de receta en compra al ledger canónico.

Comprar un producto con receta consume sus componentes vía ADJUSTMENT_OUT
canónico (no movimientos_inventario legacy), idempotente por operation_id.

FASE 2 (2026-09-17): la receta sale del catálogo canónico de Productos.
Estas pruebas sembraban la tabla LEGACY `product_recipes`, que era de donde leía
el puente — y fijaban así como contrato la fuente equivocada: nada en producción
escribe esa tabla. Ahora siguen sembrando lo heredado pero pasan por la
**migración 152**, que es lo que le ocurrió a toda base real; y el caso central
nuevo, `test_a_recipe_created_in_products_explodes_on_purchase`, es el que
fallaba antes: una receta dada de alta por la vía de Productos.
"""

import importlib
import sqlite3
from decimal import Decimal

import pytest

from backend.application.event_handlers.inventory.purchase_recipe_explosion_bridge import (
    CanonicalPurchaseRecipeExplosionHandler,
)
from backend.application.inventory.queries import InventoryAvailabilityQueryService
from backend.application.inventory.use_cases import PostInventoryMovementUseCase
from backend.application.products.authorization.policy import ProductsAuthorizationPolicy
from backend.application.products.commands.product_recipe_commands import (
    CreateRecipeCommand,
    RecipeVersionTransitionCommand,
)
from backend.application.products.use_cases.product_recipe_use_cases import (
    ActivateRecipeVersionUseCase,
    ApproveRecipeVersionUseCase,
    CreateProductRecipeUseCase,
    SubmitRecipeVersionUseCase,
)
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement, InventoryMovementLine)
from backend.domain.inventory.enums import MovementType
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from backend.infrastructure.db.schema.products_schema import create_products_schema
from backend.shared.ids import new_uuid

_152 = importlib.import_module(
    "migrations.standalone.152_products_recipes_backfill_from_legacy")
_265 = importlib.import_module("migrations.standalone.265_repair_backfilled_recipe_types")


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_inventory_schema(c)
    create_products_schema(c)
    yield c
    c.close()


@pytest.fixture
def legacy_conn(conn):
    """Receta sembrada en el catálogo LEGACY y migrada por la 152, como en
    cualquier instalación real que la tuviera."""
    conn.execute("CREATE TABLE product_recipes (id TEXT PRIMARY KEY, base_product_id TEXT,"
                 " is_active INT DEFAULT 1)")
    conn.execute("CREATE TABLE product_recipe_components (id TEXT PRIMARY KEY, recipe_id TEXT,"
                 " component_product_id TEXT, cantidad REAL)")
    conn.execute("INSERT INTO product_recipes VALUES ('r1','marinado',1)")
    conn.execute("INSERT INTO product_recipe_components VALUES ('c1','r1','pollo',2),"
                 " ('c2','r1','marinada',1)")
    conn.commit()
    # Igual que el motor de migraciones: la 152 copia y la 265 repara los tipos
    # que la 152 dejaba inválidos (sin la 265 la receta migrada es ilegible).
    _152.run(conn)
    _265.run(conn)
    return conn


class _AllowAll:
    def has_permission(self, user_id, code):
        return True


def _recipe_in_products(conn, *, product_id, components, activate=True):
    """Alta por la vía de Productos: crear → enviar → aprobar → activar."""
    auth = ProductsAuthorizationPolicy(_AllowAll())
    creada = CreateProductRecipeUseCase(conn, auth).execute(CreateRecipeCommand(
        operation_id=new_uuid(), product_id=product_id, recipe_type="PRODUCTION_BOM",
        name="Receta", user_id="alice",
        components=[{"component_product_id": pid, "quantity": qty, "unit_id": new_uuid()}
                    for pid, qty in components]))
    assert creada.success, creada.message
    if activate:
        for caso, usuario in ((SubmitRecipeVersionUseCase, "alice"),
                              (ApproveRecipeVersionUseCase, "bob"),
                              (ActivateRecipeVersionUseCase, "bob")):
            r = caso(conn, auth).execute(RecipeVersionTransitionCommand(
                operation_id=new_uuid(), version_id=creada.version_id, user_id=usuario))
            assert r.success, r.message
    return creada.version_id


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


def _payload(qty="3", event_id="gr-1", product_id="marinado"):
    return {"event_id": event_id, "warehouse_id": "b1", "user_id": "u1",
            "lines": [{"product_id": product_id, "quantity": qty}]}


def test_explosion_consumes_components_canonically(legacy_conn):
    conn = legacy_conn
    _seed(conn, "pollo", "20")
    _seed(conn, "marinada", "20")
    CanonicalPurchaseRecipeExplosionHandler(conn).handle(_payload(qty="3"))
    assert _avail(conn, "pollo") == Decimal("14")      # 20 − 2*3
    assert _avail(conn, "marinada") == Decimal("17")   # 20 − 1*3
    assert conn.execute("SELECT COUNT(*) FROM inventory_ledger"
                        " WHERE operation_id='gr-1:marinado:recipe'").fetchone()[0] == 1


def test_explosion_idempotent(legacy_conn):
    conn = legacy_conn
    _seed(conn, "pollo", "20")
    _seed(conn, "marinada", "20")
    CanonicalPurchaseRecipeExplosionHandler(conn).handle(_payload(event_id="gr-1"))
    CanonicalPurchaseRecipeExplosionHandler(conn).handle(_payload(event_id="gr-1"))
    assert _avail(conn, "pollo") == Decimal("14")  # consumed once


def test_no_recipe_is_noop(legacy_conn):
    CanonicalPurchaseRecipeExplosionHandler(legacy_conn).handle(
        _payload(product_id="sinreceta"))
    assert legacy_conn.execute("SELECT COUNT(*) FROM inventory_ledger").fetchone()[0] == 0


def test_a_recipe_created_in_products_explodes_on_purchase(conn):
    """EL HUECO DE LA FASE 2. Antes el puente leía sólo los catálogos legacy, que
    nadie escribe; una receta dada de alta en Productos no se aplicaba nunca."""
    producto, pollo, marinada = new_uuid(), new_uuid(), new_uuid()
    _recipe_in_products(conn, product_id=producto,
                        components=[(pollo, "2"), (marinada, "1")])
    _seed(conn, pollo, "20")
    _seed(conn, marinada, "20")
    CanonicalPurchaseRecipeExplosionHandler(conn).handle(
        _payload(qty="3", product_id=producto))
    assert _avail(conn, pollo) == Decimal("14")
    assert _avail(conn, marinada) == Decimal("17")


def test_a_draft_recipe_does_not_explode(conn):
    """Consumir según una fórmula que nadie aprobó es lo que Ventas ya se niega
    a hacer; comprar sigue la misma regla."""
    producto, pollo = new_uuid(), new_uuid()
    _recipe_in_products(conn, product_id=producto, components=[(pollo, "2")],
                        activate=False)
    CanonicalPurchaseRecipeExplosionHandler(conn).handle(_payload(product_id=producto))
    assert conn.execute("SELECT COUNT(*) FROM inventory_ledger").fetchone()[0] == 0


def test_without_the_products_schema_nothing_explodes():
    """Una base sin el esquema de Productos no puede tumbar la recepción de la
    compra: no hay recetas, no hay nada que consumir."""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_inventory_schema(c)
    CanonicalPurchaseRecipeExplosionHandler(c).handle(_payload())
    assert c.execute("SELECT COUNT(*) FROM inventory_ledger").fetchone()[0] == 0
    c.close()
