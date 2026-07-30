"""PROD corte de legacy (repoint batch 4) — costo de plantilla de compra canónico.

`ProveedorRepository.get_plantilla_items` unía `plantillas_compra_items` con la
tabla legacy `productos` para traer `nombre` y `precio_compra`. Ahora lee el
nombre del maestro canónico `products` y el costo de `product_cost`
(`average_cost`, sucursal global `''`, poblado por el backfill 150), preservando
las claves de salida y el tipo float (CAST a REAL).
"""

import sqlite3

import pytest

from backend.shared.ids import new_uuid


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    from migrations import engine
    engine.up(c)
    # El repoint es un SELECT puro; deshabilitamos FK sólo para sembrar filas
    # mínimas sin tener que satisfacer todos los catálogos (units, plantilla padre).
    c.execute("PRAGMA foreign_keys=OFF")
    yield c
    c.close()


def _seed(conn):
    pid = new_uuid()
    conn.execute(
        "INSERT INTO products (id, code, name, name_normalized, product_type, "
        "lifecycle_status, base_unit_id) VALUES (?,?,?,?,?,?,?)",
        (pid, "P-1", "Costilla de res", "costilla de res", "RESALE_PRODUCT",
         "ACTIVE", "kg"))
    conn.execute(
        "INSERT INTO product_cost (id, product_id, branch_id, average_cost, "
        "average_cost_currency, cost_method) VALUES (?,?,?,?,?,?)",
        (new_uuid(), pid, "", "185.50", "MXN", "AVERAGE"))
    plantilla_id = new_uuid()
    conn.execute(
        "INSERT INTO plantillas_compra_items (id, plantilla_id, producto_id, "
        "cantidad, costo_unitario) VALUES (?,?,?,?,?)",
        (new_uuid(), plantilla_id, pid, 3.0, 180.0))
    conn.commit()
    return plantilla_id, pid


def test_get_plantilla_items_reads_name_and_cost_from_canonical(conn):
    from repositories.proveedor_repository import ProveedorRepository

    plantilla_id, pid = _seed(conn)
    items = ProveedorRepository(conn).get_plantilla_items(plantilla_id)
    assert len(items) == 1
    row = items[0]
    assert row["producto_id"] == pid
    assert row["nombre"] == "Costilla de res"          # de products.name
    assert row["precio_compra"] == pytest.approx(185.50)  # de product_cost (float)
    assert isinstance(row["precio_compra"], float)
    assert row["costo_unitario"] == pytest.approx(180.0)  # de la línea de plantilla


def test_missing_cost_defaults_to_zero_not_crash(conn):
    from repositories.proveedor_repository import ProveedorRepository

    pid = new_uuid()
    conn.execute(
        "INSERT INTO products (id, code, name, name_normalized, product_type, "
        "lifecycle_status, base_unit_id) VALUES (?,?,?,?,?,?,?)",
        (pid, "P-2", "Sin costo", "sin costo", "RESALE_PRODUCT", "ACTIVE", "kg"))
    plantilla_id = new_uuid()
    conn.execute(
        "INSERT INTO plantillas_compra_items (id, plantilla_id, producto_id, "
        "cantidad, costo_unitario) VALUES (?,?,?,?,?)",
        (new_uuid(), plantilla_id, pid, 1.0, 0.0))
    conn.commit()
    items = ProveedorRepository(conn).get_plantilla_items(plantilla_id)
    assert items[0]["precio_compra"] == pytest.approx(0.0)
