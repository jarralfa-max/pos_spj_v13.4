"""Flujo forecast → sugerencia de compra: lecturas canónicas con UUID.

Repunte P0-B: `PurchasePlanningReadService` dejó de leer la tabla legacy
`productos`. Ahora la lista de candidatos usa la búsqueda canónica de productos
comprables (`products`) y la existencia lee `inventory_balances` (canónico). El
fixture siembra el modelo canónico (además del legacy compras/ventas que siguen
alimentando costo/historial).
"""
from __future__ import annotations

from backend.application.queries.purchase_planning_query_service import (
    PurchasePlanningReadService,
)
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from backend.infrastructure.db.schema.products_schema import create_products_schema
from backend.shared.ids import new_uuid
from tests.integration._born_clean_db import make_db


def _canonical_db():
    conn = make_db()
    create_products_schema(conn)
    create_inventory_schema(conn)
    conn.commit()
    return conn


def _seed(conn):
    producto_id, sucursal_id = new_uuid(), new_uuid()
    # maestro canónico (comprable + ACTIVE) — la lista de forecast lo toma de aquí
    conn.execute(
        "INSERT INTO products (id, code, name, name_normalized, product_type, "
        "lifecycle_status, base_unit_id, sellable, purchasable, inventory_managed) "
        "VALUES (?,?,?,?,?,?,?,1,1,1)",
        (producto_id, "P-ARR", "Arrachera", "arrachera", "RAW_MATERIAL", "ACTIVE", "kg"))
    # existencia canónica 14.5 (una sucursal)
    conn.execute(
        "INSERT INTO inventory_balances (id, product_id, branch_id, warehouse_id, "
        "location_id, lot_id, inventory_status, quantity, reserved_quantity, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,datetime('now'))",
        (new_uuid(), producto_id, sucursal_id, "w1", "", "", "AVAILABLE", "14.5", "0"))
    # legacy compras/ventas (costo e historial siguen leyendo estas tablas)
    compra_id = new_uuid()
    conn.execute(
        "INSERT INTO compras (id, folio, total, usuario) VALUES (?, 'C-9', 900.0, 'u')",
        (compra_id,),
    )
    conn.execute(
        "INSERT INTO detalles_compra (id, compra_id, producto_id, cantidad, "
        " precio_unitario, subtotal) VALUES (?, ?, ?, 10, 90.0, 900.0)",
        (new_uuid(), compra_id, producto_id),
    )
    venta_id = new_uuid()
    conn.execute(
        "INSERT INTO ventas (id, folio, sucursal_id, total, estado, fecha) "
        "VALUES (?, 'F-9', ?, 180, 'completada', date('now','-2 days'))",
        (venta_id, sucursal_id),
    )
    conn.execute(
        "INSERT INTO detalles_venta (id, venta_id, producto_id, cantidad, precio_unitario, subtotal) "
        "VALUES (?, ?, ?, 2.0, 90.0, 180.0)",
        (new_uuid(), venta_id, producto_id),
    )
    conn.commit()
    return producto_id, sucursal_id


def test_planning_reads_feed_purchase_suggestion():
    conn = _canonical_db()
    producto_id, sucursal_id = _seed(conn)
    reads = PurchasePlanningReadService(conn)

    productos = reads.list_forecastable_products(sucursal_id)
    assert any(p["id"] == producto_id for p in productos)
    assert all(isinstance(p["id"], str) for p in productos)

    assert reads.last_purchase_cost(producto_id) == 90.0
    assert reads.current_stock(producto_id) == 14.5

    historia = reads.sales_history(producto_id, sucursal_id, days=30)
    assert len(historia) == 1
    assert historia[0]["total_vendido"] == 2.0


def test_reads_are_safe_with_unknown_product():
    conn = _canonical_db()
    reads = PurchasePlanningReadService(conn)
    assert reads.last_purchase_cost(new_uuid()) == 0.0
    assert reads.current_stock(new_uuid()) == 0.0
    assert reads.sales_history(new_uuid(), new_uuid(), 30) == []
