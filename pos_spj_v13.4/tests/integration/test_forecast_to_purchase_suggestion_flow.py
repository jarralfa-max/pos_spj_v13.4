"""Flujo forecast → sugerencia de compra: lecturas canónicas con UUID."""
from __future__ import annotations

from backend.application.queries.purchase_planning_query_service import (
    PurchasePlanningReadService,
)
from backend.shared.ids import new_uuid
from tests.integration._born_clean_db import make_db


def _seed(conn):
    producto_id, sucursal_id = new_uuid(), new_uuid()
    conn.execute(
        "INSERT INTO productos (id, nombre, activo, existencia) "
        "VALUES (?, 'Arrachera', 1, 14.5)",
        (producto_id,),
    )
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
    return producto_id, sucursal_id


def test_planning_reads_feed_purchase_suggestion():
    conn = make_db()
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
    conn = make_db()
    reads = PurchasePlanningReadService(conn)
    assert reads.last_purchase_cost(new_uuid()) == 0.0
    assert reads.current_stock(new_uuid()) == 0.0
    assert reads.sales_history(new_uuid(), new_uuid(), 30) == []
