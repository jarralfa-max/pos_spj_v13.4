"""PROD-19 corte paso 1 — backfill productos → products (mapeo, idempotencia, guardrail)."""

import importlib
import sqlite3

import pytest

from backend.infrastructure.db.schema.products_schema import create_products_schema

_mig = importlib.import_module("migrations.standalone.148_products_backfill_from_legacy")


def _legacy_schema(c):
    # subconjunto de columnas del maestro legacy `productos` (m000)
    c.execute("""
        CREATE TABLE productos (
            id TEXT PRIMARY KEY, codigo TEXT, codigo_barras TEXT, nombre TEXT,
            descripcion TEXT, categoria TEXT, precio REAL, existencia REAL,
            unidad TEXT, tipo_producto TEXT, es_compuesto INTEGER, es_subproducto INTEGER,
            oculto INTEGER, sucursal_id TEXT, activo INTEGER, is_active INTEGER,
            es_paquete INTEGER, deleted_at DATETIME, nombre_normalizado TEXT,
            fecha_alta DATETIME, ultima_actualizacion DATETIME, es_carnico INTEGER,
            unidad_peso TEXT, permite_receta INTEGER, es_vendible INTEGER,
            es_inventariable INTEGER)
    """)


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_products_schema(c)
    _legacy_schema(c)
    c.commit()
    yield c
    c.close()


def _insert_legacy(c, **kw):
    base = dict(id="u1", codigo="ABR-1", nombre="Refresco Cola", descripcion="600ml",
                unidad="pza", precio=25.5, existencia=100.0, activo=1, es_vendible=1,
                es_inventariable=1, es_carnico=0, es_paquete=0, es_subproducto=0)
    base.update(kw)
    cols = ",".join(base)
    ph = ",".join("?" for _ in base)
    c.execute(f"INSERT INTO productos ({cols}) VALUES ({ph})", tuple(base.values()))


def test_backfill_maps_core_fields(conn):
    _insert_legacy(conn)
    _mig.run(conn)
    row = conn.execute("SELECT * FROM products WHERE id='u1'").fetchone()
    assert row["code"] == "ABR-1" and row["name"] == "Refresco Cola"
    assert row["base_unit_id"] == "PZA" and row["lifecycle_status"] == "ACTIVE"
    assert row["product_type"] == "RESALE_PRODUCT" and row["sellable"] == 1


def test_backfill_does_not_copy_price_or_stock(conn):
    _insert_legacy(conn, precio=99.0, existencia=50.0)
    _mig.run(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(products)")}
    assert "precio" not in cols and "existencia" not in cols  # esquema canónico limpio


def test_backfill_type_mapping(conn):
    _insert_legacy(conn, id="pk", codigo="K1", es_paquete=1)
    _insert_legacy(conn, id="sb", codigo="S1", es_subproducto=1)
    _insert_legacy(conn, id="mt", codigo="M1", es_carnico=1, unidad_peso="kg")
    _mig.run(conn)
    got = {r["id"]: r["product_type"] for r in conn.execute("SELECT id, product_type FROM products")}
    assert got["pk"] == "VIRTUAL_BUNDLE"
    assert got["sb"] == "BY_PRODUCT"
    assert got["mt"] == "RAW_MATERIAL"
    mt = conn.execute("SELECT catch_weight_enabled, lot_controlled FROM products WHERE id='mt'").fetchone()
    assert mt["catch_weight_enabled"] == 1 and mt["lot_controlled"] == 1


def test_backfill_deleted_becomes_archived(conn):
    _insert_legacy(conn, id="d1", codigo="D1", deleted_at="2024-01-01")
    _mig.run(conn)
    assert conn.execute("SELECT lifecycle_status FROM products WHERE id='d1'"
                        ).fetchone()[0] == "ARCHIVED"


def test_backfill_is_idempotent(conn):
    _insert_legacy(conn)
    _mig.run(conn)
    _mig.run(conn)  # segunda vez no duplica ni falla
    assert conn.execute("SELECT COUNT(*) FROM products WHERE id='u1'").fetchone()[0] == 1


def test_backfill_generates_code_when_missing(conn):
    _insert_legacy(conn, id="nocode", codigo=None, nombre="Sin código")
    _mig.run(conn)
    row = conn.execute("SELECT code FROM products WHERE id='nocode'").fetchone()
    assert row["code"].startswith("P-")
