"""Stock cutover — `repositories/productos.py` deja de leer/escribir
`productos.existencia`/`stock_minimo`.

Gap real detectado en la auditoría del bounded context de Inventario
(2026-09-03): el repositorio legacy de Productos seguía siendo fuente y
sumidero de stock por SQL directo, violando la regla "el stock vive sólo en
Inventario" que ya aplica en el resto del sistema
(`test_product_master_does_not_store_stock`). Este test prueba que:

- las lecturas (`get_all`, `get_by_id`, `get_by_barcode`, `get_for_sale`,
  `buscar_exacto_para_scanner`, `buscar_para_scanner`) devuelven `existencia`/
  `stock_minimo` derivados del ledger canónico (`inventory_balances`/
  `inventory_replenishment_rule`), no de las columnas legacy — con las mismas
  claves de salida (cero cambio de contrato para los consumidores reales:
  `modulos/spj_product_search.py`);
- las escrituras (`create`, `update`) ya no persisten `existencia`/
  `stock_minimo` en `productos`, aunque el caller los pase en el dict.
"""

from __future__ import annotations

import sqlite3

import pytest

from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from repositories.productos import ProductoRepository


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE productos (
            id TEXT PRIMARY KEY, nombre TEXT, nombre_normalizado TEXT,
            precio REAL DEFAULT 0, precio_venta REAL DEFAULT 0, precio_kilo REAL DEFAULT 0,
            precio_compra REAL DEFAULT 0,
            existencia REAL DEFAULT 999, stock_minimo REAL DEFAULT 999,
            unidad TEXT DEFAULT 'kg', tipo TEXT, categoria TEXT, descripcion TEXT,
            codigo TEXT, codigo_barras TEXT,
            oculto INTEGER DEFAULT 0, activo INTEGER DEFAULT 1,
            es_compuesto INTEGER DEFAULT 0, es_subproducto INTEGER DEFAULT 0,
            producto_padre_id TEXT, imagen_path TEXT,
            is_active INTEGER DEFAULT 1, deleted_at TEXT, fecha_actualizacion TEXT
        );
        CREATE TABLE logs (id TEXT PRIMARY KEY, modulo TEXT, accion TEXT, detalles TEXT, usuario TEXT);
        """
    )
    create_inventory_schema(conn)
    conn.commit()
    return conn


def _seed_producto(db, pid: str, *, existencia_legacy=999, stock_minimo_legacy=999, **extra):
    cols = dict(id=pid, nombre=f"Producto {pid}", codigo=pid, codigo_barras=pid,
                precio=10, precio_venta=10, precio_kilo=10, precio_compra=5,
                existencia=existencia_legacy, stock_minimo=stock_minimo_legacy,
                unidad="kg", tipo="simple", categoria="cat", descripcion="")
    cols.update(extra)
    placeholders = ",".join("?" for _ in cols)
    db.execute(
        f"INSERT INTO productos ({','.join(cols)}) VALUES ({placeholders})",
        tuple(cols.values()),
    )


def _seed_canonical_stock(db, pid: str, *, available="7", reorder="2"):
    db.execute(
        "INSERT INTO inventory_balances (id, product_id, branch_id, warehouse_id, "
        "inventory_status, quantity, reserved_quantity, updated_at) "
        "VALUES (?,?,?,?, 'AVAILABLE', ?, '0', datetime('now'))",
        (f"bal-{pid}", pid, "b1", "w1", available))
    db.execute(
        "INSERT INTO inventory_replenishment_rule (id, product_id, branch_id, "
        "warehouse_id, reorder_point, min_quantity, active, created_at) "
        "VALUES (?,?,?,?,?, '0', 1, datetime('now'))",
        (f"rule-{pid}", pid, "", "", reorder))


def test_get_all_uses_canonical_stock_not_legacy_column(db):
    _seed_producto(db, "p1")
    _seed_canonical_stock(db, "p1", available="7", reorder="2")
    db.commit()

    rows = ProductoRepository(db).get_all()
    assert len(rows) == 1
    assert rows[0]["existencia"] == 7.0
    assert rows[0]["stock_minimo"] == 2.0


def test_get_by_id_uses_canonical_stock(db):
    _seed_producto(db, "p1")
    _seed_canonical_stock(db, "p1", available="11", reorder="4")
    db.commit()

    row = ProductoRepository(db).get_by_id("p1")
    assert row["existencia"] == 11.0
    assert row["stock_minimo"] == 4.0


def test_get_for_sale_uses_canonical_stock(db):
    _seed_producto(db, "p1")
    _seed_canonical_stock(db, "p1", available="3")
    db.commit()

    rows = ProductoRepository(db).get_for_sale()
    assert rows[0]["existencia"] == 3.0


def test_get_by_barcode_uses_canonical_stock(db):
    _seed_producto(db, "p1")
    _seed_canonical_stock(db, "p1", available="9")
    db.commit()

    row = ProductoRepository(db).get_by_barcode("p1")
    assert row["existencia"] == 9.0


def test_scanner_search_methods_use_canonical_stock(db):
    _seed_producto(db, "p1")
    _seed_canonical_stock(db, "p1", available="4.5")
    db.commit()

    repo = ProductoRepository(db)
    exact = repo.buscar_exacto_para_scanner("p1")
    assert exact["existencia"] == 4.5

    fuzzy = repo.buscar_para_scanner("Producto")
    assert fuzzy[0]["existencia"] == 4.5


def test_product_with_no_canonical_balance_reports_zero_not_legacy_value(db):
    # La columna legacy sigue en 999 (nunca tocada); sin balance canónico el
    # disponible real es 0 — no debe leerse el valor legacy huérfano.
    _seed_producto(db, "p1", existencia_legacy=999, stock_minimo_legacy=999)
    db.commit()

    row = ProductoRepository(db).get_by_id("p1")
    assert row["existencia"] == 0.0
    assert row["stock_minimo"] == 0.0


def test_create_does_not_write_existencia_or_stock_minimo(db):
    new_id = ProductoRepository(db).create(
        {"nombre": "Nuevo", "precio": 20, "existencia": 500, "stock_minimo": 50}, "qa")
    row = db.execute(
        "SELECT existencia, stock_minimo FROM productos WHERE id=?", (new_id,)
    ).fetchone()
    # La columna conserva su DEFAULT de esquema (999 en este fixture) — el
    # valor 500/50 que pasó el caller nunca llega a la tabla.
    assert row["existencia"] == 999
    assert row["stock_minimo"] == 999


def test_update_does_not_write_existencia_or_stock_minimo(db):
    _seed_producto(db, "p1", existencia_legacy=1, stock_minimo_legacy=1)
    db.commit()

    ProductoRepository(db).update(
        "p1", {"nombre": "Editado", "precio": 30, "existencia": 500, "stock_minimo": 50}, "qa")
    row = db.execute(
        "SELECT nombre, existencia, stock_minimo FROM productos WHERE id=?", ("p1",)
    ).fetchone()
    assert row["nombre"] == "Editado"
    # No tocado por el UPDATE — sigue en el valor original, no en 500/50.
    assert row["existencia"] == 1
    assert row["stock_minimo"] == 1
