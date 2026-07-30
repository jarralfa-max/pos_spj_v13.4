"""PROD corte de legacy — migración 167 enlaza products.category_id desde legacy.

Con las categorías canónicas ya respaldadas (166), 167 asigna a cada producto su
`category_id` cuando la `categoria` legacy normalizada coincide con una categoría
canónica. Aditiva, idempotente y sólo toca `category_id` NULL.
"""

import importlib
import sqlite3

from backend.infrastructure.db.schema.products_schema import create_products_schema

_167 = importlib.import_module(
    "migrations.standalone.167_products_category_id_backfill")


def _db():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_products_schema(c)
    c.execute("CREATE TABLE productos (id TEXT PRIMARY KEY, categoria TEXT)")
    # categoría canónica ya respaldada (como haría 166)
    c.execute("INSERT INTO product_categories (id, code, name, name_normalized) "
              "VALUES ('c-aves','AVES','Aves','aves')")
    # productos legacy con la misma categoría (ids preservados por backfill 148)
    c.execute("INSERT INTO productos VALUES ('p1','Aves')")
    c.execute("INSERT INTO productos VALUES ('p2','SinCanonica')")
    for pid in ("p1", "p2"):
        c.execute("INSERT INTO products (id, code, name, name_normalized, "
                  "product_type, lifecycle_status, base_unit_id) VALUES "
                  "(?,?,?,?,?,?,?)",
                  (pid, pid.upper(), pid, pid, "RESALE_PRODUCT", "ACTIVE", "pza"))
    c.commit()
    return c


def test_backfill_links_category_id_when_match_exists():
    c = _db()
    _167.run(c)
    p1 = c.execute("SELECT category_id FROM products WHERE id='p1'").fetchone()[0]
    p2 = c.execute("SELECT category_id FROM products WHERE id='p2'").fetchone()[0]
    assert p1 == "c-aves"     # enlazado a la categoría canónica
    assert p2 is None         # sin categoría canónica coincidente → queda NULL


def test_backfill_is_idempotent_and_preserves_manual_links():
    c = _db()
    # un enlace manual previo no debe sobreescribirse
    c.execute("UPDATE products SET category_id='manual' WHERE id='p1'")
    c.commit()
    _167.run(c)
    _167.run(c)
    assert c.execute(
        "SELECT category_id FROM products WHERE id='p1'").fetchone()[0] == "manual"
