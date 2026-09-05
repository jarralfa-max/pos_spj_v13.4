"""PROD corte de legacy (repoint batch 3) — categorías canónicas.

La migración 166 respalda `product_categories` desde las categorías de texto
libre de `productos`, y `BiDashboardQueryService.filter_options` lee las
categorías del catálogo canónico en vez de la tabla legacy. Con el backfill, la
lista de categorías es equivalente a la histórica (cero regresión), y el
backfill es idempotente.
"""

import importlib
import sqlite3

from backend.infrastructure.db.schema.products_schema import create_products_schema

_166 = importlib.import_module(
    "migrations.standalone.166_product_categories_backfill_from_legacy")


def _db_with_legacy_categories():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_products_schema(conn)
    conn.execute("CREATE TABLE productos (id TEXT PRIMARY KEY, nombre TEXT, "
                 "categoria TEXT, activo INTEGER DEFAULT 1)")
    conn.executemany(
        "INSERT INTO productos (id, nombre, categoria) VALUES (?,?,?)",
        [("p1", "Pechuga", "Aves"), ("p2", "Pierna", "Aves"),
         ("p3", "Arrachera", "Res"), ("p4", "Sin categoria", ""),
         ("p5", "Nula", None)])
    conn.commit()
    return conn


def test_backfill_creates_canonical_categories_from_legacy():
    conn = _db_with_legacy_categories()
    _166.run(conn)
    names = [r[0] for r in conn.execute(
        "SELECT name FROM product_categories ORDER BY name")]
    assert names == ["Aves", "Res"]  # distintas, no vacías/nulas
    # raíces born-clean: id UUID, code único no vacío, path materializado.
    rows = conn.execute(
        "SELECT id, code, path, depth FROM product_categories").fetchall()
    for r in rows:
        assert r["id"] and r["code"] and r["path"] == f"/{r['id']}/" and r["depth"] == 0


def test_backfill_is_idempotent():
    conn = _db_with_legacy_categories()
    _166.run(conn)
    _166.run(conn)  # segunda corrida no duplica
    assert conn.execute(
        "SELECT COUNT(*) FROM product_categories").fetchone()[0] == 2


def test_backfill_skips_existing_category_by_name():
    conn = _db_with_legacy_categories()
    conn.execute(
        "INSERT INTO product_categories (id, code, name, name_normalized, path) "
        "VALUES ('c-aves','AVES','Aves','aves','/c-aves/')")
    conn.commit()
    _166.run(conn)
    # 'Aves' ya existía → no se duplica; sólo se agrega 'Res'.
    aves = conn.execute(
        "SELECT COUNT(*) FROM product_categories WHERE name_normalized='aves'").fetchone()[0]
    assert aves == 1
    assert conn.execute("SELECT COUNT(*) FROM product_categories").fetchone()[0] == 2


def test_bi_filter_options_reads_canonical_categories():
    from backend.application.analytics.queries.bi_dashboard_query_service import (
        BiDashboardQueryService,
    )

    conn = _db_with_legacy_categories()
    conn.execute("CREATE TABLE sucursales (id TEXT, nombre TEXT, activa INTEGER)")
    conn.execute("CREATE TABLE ventas (id TEXT, forma_pago TEXT)")
    _166.run(conn)

    class _Sales:
        _conn = conn

    svc = BiDashboardQueryService.__new__(BiDashboardQueryService)
    svc.sales = _Sales()
    opts = svc.filter_options()
    assert opts["categories"] == ["Aves", "Res"]  # del catálogo canónico
    # No dependió de la tabla legacy `productos` para las categorías.
