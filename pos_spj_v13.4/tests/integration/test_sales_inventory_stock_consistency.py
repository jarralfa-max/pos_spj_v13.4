from __future__ import annotations

import sqlite3

from backend.application.queries.inventory_query_service import InventoryQueryService
from backend.application.services.inventory_application_service import InventoryApplicationService
from backend.infrastructure.db.repositories.inventory_repository import InventoryRepository
from core.services.recipes.recipe_resolver import RecipeResolver
from core.services.sales.product_catalog_query_service import ProductCatalogQueryService
from core.services.stock_reservation_service import StockReservationService


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE productos (
            id INTEGER PRIMARY KEY,
            nombre TEXT,
            precio REAL,
            existencia REAL,
            unidad TEXT,
            categoria TEXT,
            stock_minimo REAL,
            imagen_path TEXT,
            es_compuesto INTEGER,
            es_subproducto INTEGER,
            codigo_barras TEXT,
            codigo TEXT,
            oculto INTEGER DEFAULT 0,
            activo INTEGER DEFAULT 1,
            tipo_producto TEXT DEFAULT 'simple'
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE inventory_stock (
            product_id INTEGER NOT NULL,
            branch_id INTEGER NOT NULL,
            quantity REAL NOT NULL DEFAULT 0,
            unit TEXT,
            updated_at TEXT,
            PRIMARY KEY(product_id, branch_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE inventory_movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operation_id TEXT NOT NULL,
            product_id INTEGER NOT NULL,
            branch_id INTEGER NOT NULL,
            movement_type TEXT NOT NULL,
            quantity REAL NOT NULL,
            stock_before REAL NOT NULL,
            stock_after REAL NOT NULL,
            unit TEXT,
            source_module TEXT,
            reference_type TEXT,
            reference_id TEXT,
            reason TEXT,
            user_name TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(operation_id, product_id, branch_id, movement_type)
        )
        """
    )
    # Legacy table intentionally present with a divergent value. Operational reads
    # must ignore it and use inventory_stock instead.
    conn.execute("CREATE TABLE branch_inventory (product_id INTEGER, branch_id INTEGER, quantity REAL)")
    conn.execute(
        """
        CREATE TABLE product_recipes (
            id INTEGER PRIMARY KEY,
            base_product_id INTEGER,
            is_active INTEGER DEFAULT 1
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE product_recipe_components (
            id INTEGER PRIMARY KEY,
            recipe_id INTEGER,
            component_product_id INTEGER,
            cantidad REAL,
            rendimiento_pct REAL,
            orden INTEGER DEFAULT 0
        )
        """
    )
    conn.execute("INSERT INTO productos VALUES (1,'Pollo',100,77,'kg','Carnes',1,'',0,0,'CB1','C1',0,1,'simple')")
    conn.execute("INSERT INTO productos VALUES (2,'Combo pollo',150,88,'pza','Combos',0,'',1,0,'CB2','C2',0,1,'compuesto')")
    conn.execute("INSERT INTO productos VALUES (3,'Sin canonical',50,88,'kg','Carnes',1,'',0,0,'CB3','C3',0,1,'simple')")
    conn.execute("INSERT INTO inventory_stock(product_id, branch_id, quantity, unit) VALUES (1,1,10,'kg')")
    conn.execute("INSERT INTO branch_inventory(product_id, branch_id, quantity) VALUES (1,1,99)")
    conn.execute("INSERT INTO branch_inventory(product_id, branch_id, quantity) VALUES (3,1,99)")
    conn.execute("INSERT INTO product_recipes(id, base_product_id, is_active) VALUES (1,2,1)")
    conn.execute("INSERT INTO product_recipe_components(recipe_id, component_product_id, cantidad, rendimiento_pct, orden) VALUES (1,1,2,0,1)")
    conn.commit()
    return conn


def _inventory_quantity(conn: sqlite3.Connection, product_id: int = 1) -> float:
    rows = InventoryQueryService(InventoryRepository(conn)).list_stock_rows(branch_id=1)
    return float(next(row[3] for row in rows if int(row[0]) == product_id))


def _catalog_quantity(conn: sqlite3.Connection, product_id: int = 1) -> float:
    rows = ProductCatalogQueryService(conn).list_visible_products(branch_id=1)
    return float(next(row["existencia"] for row in rows if int(row["id"]) == product_id))


def test_sales_inventory_recipe_and_reservations_share_inventory_stock() -> None:
    conn = _db()

    assert _inventory_quantity(conn, 1) == 10.0
    assert _catalog_quantity(conn, 1) == 10.0
    assert RecipeResolver(conn)._get_stock(1, 1) == 10.0
    assert RecipeResolver(conn).virtual_availability(2, 1) == 5.0

    reservations = StockReservationService(conn, branch_id=1)
    reserva_id = reservations.reservar("R-1", [{"id": 1, "cantidad": 2}])
    assert reserva_id > 0
    assert reservations.stock_disponible(1) == 8.0
    # Decision: POS catalog displays physical stock. Sale availability is physical
    # stock minus active reservations and is exposed by StockReservationService.
    assert _catalog_quantity(conn, 1) == 10.0


def test_missing_inventory_stock_row_is_zero_and_ignores_legacy_stock_columns() -> None:
    conn = _db()

    assert _inventory_quantity(conn, 3) == 0.0
    assert _catalog_quantity(conn, 3) == 0.0
    assert RecipeResolver(conn)._get_stock(3, 1) == 0.0


def test_completed_sale_updates_inventory_stock_movements_and_sales_catalog() -> None:
    conn = _db()
    inventory_service = InventoryApplicationService(repository=InventoryRepository(conn))

    result = inventory_service.decrease_stock(
        product_id=1,
        branch_id=1,
        quantity=4,
        unit="kg",
        reason="Venta completada",
        operation_id="sale-completed-1",
        source_module="sales",
        reference_type="VENTA",
        reference_id="V-1",
        user_name="cajero",
    )

    assert result.success is True
    assert result.stock_before == 10.0
    assert result.stock_after == 6.0
    assert _inventory_quantity(conn, 1) == 6.0
    assert _catalog_quantity(conn, 1) == 6.0
    movement = conn.execute(
        """
        SELECT movement_type, quantity, stock_before, stock_after, source_module
        FROM inventory_movements
        WHERE operation_id='sale-completed-1' AND product_id=1 AND branch_id=1
        """
    ).fetchone()
    assert dict(movement) == {
        "movement_type": "DECREASE",
        "quantity": 4.0,
        "stock_before": 10.0,
        "stock_after": 6.0,
        "source_module": "sales",
    }
