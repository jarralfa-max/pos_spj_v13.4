"""PROD-22 — migración 325: retira el esquema legacy de Productos, sin perder datos."""

from __future__ import annotations

import importlib
import sqlite3

import pytest

m325 = importlib.import_module("migrations.standalone.325_drop_legacy_products_schema")


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.execute("PRAGMA foreign_keys=ON")
    c.executescript("""
        CREATE TABLE productos (id TEXT PRIMARY KEY, nombre TEXT, precio REAL, existencia REAL);
        CREATE TABLE branch_products (id TEXT PRIMARY KEY,
            product_id TEXT REFERENCES productos(id));
        CREATE TABLE recetas (id TEXT PRIMARY KEY, producto_id TEXT);
        CREATE TABLE rendimiento_pollo (id TEXT PRIMARY KEY);
        CREATE TABLE historial_precios (id TEXT PRIMARY KEY,
            producto_id TEXT REFERENCES productos(id));
        CREATE TABLE products (id TEXT PRIMARY KEY, name TEXT);
        CREATE VIEW v_productos_activos AS SELECT id, nombre FROM productos;
        CREATE TRIGGER trg_historial_precio_venta AFTER UPDATE OF precio ON productos
        BEGIN INSERT INTO historial_precios (id, producto_id) VALUES (NEW.id, NEW.id); END;
        CREATE VIEW v_products AS SELECT id, name FROM products;
    """)
    yield c
    c.close()


def _names(c, kind="table"):
    return {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type=?", (kind,))}


def test_drops_empty_legacy_tables_with_their_views_and_triggers(conn):
    dropped = m325.run(conn)
    assert {"productos", "branch_products", "recetas", "rendimiento_pollo",
            "historial_precios"} == set(dropped)
    assert "productos" not in _names(conn) and "products" in _names(conn)
    assert "v_productos_activos" not in _names(conn, "view")
    assert "v_products" in _names(conn, "view")          # lo canónico no se toca
    assert "trg_historial_precio_venta" not in _names(conn, "trigger")
    assert m325.run(conn) == []                           # idempotente


def test_keeps_everything_if_any_legacy_table_has_rows(conn):
    conn.execute("INSERT INTO recetas VALUES ('r1','p1')")
    assert m325.run(conn) == []
    assert {"productos", "recetas", "historial_precios"} <= _names(conn)
    assert "v_productos_activos" in _names(conn, "view")
    assert m325.blockers(conn) == ["recetas tiene 1 fila(s)"]


def test_keeps_everything_if_a_live_table_references_the_legacy_master(conn):
    conn.execute("CREATE TABLE ventas_nuevas (id TEXT PRIMARY KEY, "
                 "producto_id TEXT REFERENCES productos(id))")
    assert m325.run(conn) == []
    assert "productos" in _names(conn)
    assert m325.blockers(conn) == ["ventas_nuevas referencia a productos"]


def test_registered_in_the_engine_after_the_permission_seed():
    from migrations import engine
    versions = [m.version for m in engine.MIGRATIONS]
    assert versions.index("325") > versions.index("324")
    assert not any("legacy_products_drop" in m.module for m in engine.MIGRATIONS)
