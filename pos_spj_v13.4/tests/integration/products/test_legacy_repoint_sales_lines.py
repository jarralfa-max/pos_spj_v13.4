"""PROD Fase 11 — repoint batch 1: las líneas de venta leen el nombre del maestro
canónico `products` (no de la tabla legacy `productos`).

`VentaRepository.get_items` y `SalesRepository.find_by_folio` unían
`detalles_venta` con la tabla legacy `productos` sólo para traer el nombre del
producto. Como el backfill 148 pobló `products.name` desde `productos.nombre`
preservando los ids UUID, y la escritura del maestro ya está flipada a
`products`, la unión canónica devuelve el mismo nombre. Estos tests fijan el
repoint: el nombre proviene de `products`, y NO existe tabla `productos`.
"""

import sqlite3
import uuid

from backend.shared.ids import new_uuid


def _conn_with_products_and_sale():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    # Maestro canónico mínimo (sin la tabla legacy `productos`).
    conn.execute(
        "CREATE TABLE products (id TEXT NOT NULL PRIMARY KEY, code TEXT NOT NULL, "
        "name TEXT NOT NULL, name_normalized TEXT, product_type TEXT, "
        "lifecycle_status TEXT, base_unit_id TEXT)")
    conn.execute(
        "CREATE TABLE ventas (id TEXT PRIMARY KEY, folio TEXT, total REAL)")
    conn.execute(
        "CREATE TABLE detalles_venta (id TEXT PRIMARY KEY, venta_id TEXT, "
        "producto_id TEXT, cantidad REAL, precio_unitario REAL, subtotal REAL, "
        "costo_unitario REAL, margen_real REAL)")
    prod_id = new_uuid()
    sale_id = new_uuid()
    conn.execute(
        "INSERT INTO products (id, code, name, name_normalized, product_type, "
        "lifecycle_status, base_unit_id) VALUES (?,?,?,?,?,?,?)",
        (prod_id, "P-1", "Pechuga de pollo", "pechuga de pollo", "RESALE_PRODUCT",
         "ACTIVE", "kg"))
    conn.execute("INSERT INTO ventas (id, folio, total) VALUES (?,?,?)",
                 (sale_id, "VNT-0001", 120.0))
    conn.execute(
        "INSERT INTO detalles_venta (id, venta_id, producto_id, cantidad, "
        "precio_unitario, subtotal, costo_unitario, margen_real) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (new_uuid(), sale_id, prod_id, 2.0, 60.0, 120.0, 40.0, 20.0))
    conn.commit()
    return conn, sale_id, prod_id


def test_venta_repository_get_items_reads_products_name():
    from repositories.ventas import VentaRepository

    conn, sale_id, prod_id = _conn_with_products_and_sale()
    items = VentaRepository(conn).get_items(sale_id)
    assert len(items) == 1
    assert items[0]["producto_nombre"] == "Pechuga de pollo"  # de products.name
    assert items[0]["producto_id"] == prod_id
    # No debe existir la tabla legacy en este esquema canónico.
    assert conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE name='productos'").fetchone()[0] == 0


def test_sales_repository_get_sale_by_folio_reads_products_name():
    from repositories.sales_repository import SalesRepository

    conn, _sale_id, _prod = _conn_with_products_and_sale()
    venta = SalesRepository(conn).get_sale_by_folio("VNT-0001")
    assert venta is not None
    assert len(venta["items"]) == 1
    assert venta["items"][0]["nombre"] == "Pechuga de pollo"  # de products.name


def test_missing_product_in_products_drops_the_line_like_before():
    """Comportamiento equivalente al INNER JOIN previo: si el producto no está en
    el maestro, la línea no aparece (igual que cuando faltaba en `productos`)."""
    from repositories.ventas import VentaRepository

    conn, sale_id, _prod = _conn_with_products_and_sale()
    orphan_sale = new_uuid()
    conn.execute("INSERT INTO ventas (id, folio, total) VALUES (?,?,?)",
                 (orphan_sale, "VNT-0002", 10.0))
    conn.execute(
        "INSERT INTO detalles_venta (id, venta_id, producto_id, cantidad, "
        "precio_unitario, subtotal, costo_unitario, margen_real) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (new_uuid(), orphan_sale, str(uuid.uuid4()), 1.0, 10.0, 10.0, 5.0, 5.0))
    conn.commit()
    assert VentaRepository(conn).get_items(orphan_sale) == []
