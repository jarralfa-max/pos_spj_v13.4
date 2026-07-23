"""PROD-4 — esquema born-clean de Productos: UUIDv7, sin stock/precio, idempotente."""

import sqlite3

import pytest

from backend.domain.products.entities.product import Product
from backend.domain.products.enums import ProductType
from backend.infrastructure.db.schema.products_schema import (
    PRODUCT_TABLES,
    create_products_schema,
    drop_products_schema,
)


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    create_products_schema(c)
    c.commit()
    yield c
    c.close()


def _columns(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


class TestSchemaShape:
    def test_all_tables_created(self, conn):
        rows = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        for t in PRODUCT_TABLES:
            assert t in rows

    def test_products_pk_is_text_uuid(self, conn):
        info = {r[1]: r[2] for r in conn.execute("PRAGMA table_info(products)")}
        assert info["id"] == "TEXT"

    def test_products_has_no_stock_or_price_columns(self, conn):
        cols = _columns(conn, "products")
        for forbidden in ("existencia", "stock", "stock_minimo", "precio",
                          "precio_compra", "precio_minimo_venta", "price", "cantidad"):
            assert forbidden not in cols

    def test_no_real_columns_anywhere(self, conn):
        # REGLA CERO/Decimal-only: ninguna columna REAL/FLOAT en el esquema.
        for table in PRODUCT_TABLES:
            for r in conn.execute(f"PRAGMA table_info({table})"):
                assert r[2].upper() not in ("REAL", "FLOAT", "DOUBLE"), \
                    f"{table}.{r[1]} es {r[2]}"

    def test_classification_stored_as_ids(self, conn):
        cols = _columns(conn, "products")
        assert "category_id" in cols and "base_unit_id" in cols and "species_id" in cols
        # sin columnas de texto libre para categoría/unidad
        assert "categoria" not in cols and "unidad" not in cols


class TestIdempotency:
    def test_create_is_idempotent(self, conn):
        create_products_schema(conn)  # segunda vez, no debe fallar
        create_products_schema(conn)
        conn.commit()

    def test_drop_lists_tables(self, conn):
        dropped = drop_products_schema(conn)
        assert set(dropped) == set(PRODUCT_TABLES)


class TestPersistRoundTrip:
    def test_insert_product_uuid_and_flags(self, conn):
        p = Product(code="ABR-001", name="Refresco Cola",
                    product_type=ProductType.RESALE_PRODUCT, base_unit_id="u-pza",
                    category_id="cat-1", sellable=True, inventory_managed=True)
        conn.execute(
            """INSERT INTO products
               (id, code, name, name_normalized, product_type, lifecycle_status,
                category_id, base_unit_id, sellable, inventory_managed)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (p.id, p.code.value, p.name.value, p.name.normalized,
             p.product_type.value, p.lifecycle_status.value, p.category_id,
             p.base_unit_id, int(p.sellable), int(p.inventory_managed)))
        conn.commit()
        row = conn.execute("SELECT * FROM products WHERE id=?", (p.id,)).fetchone()
        assert row["code"] == "ABR-001" and row["sellable"] == 1

    def test_code_unique_enforced(self, conn):
        args = ("id1", "DUP", "N", "n", "RESALE_PRODUCT", "DRAFT", "u1")
        conn.execute(
            "INSERT INTO products (id,code,name,name_normalized,product_type,"
            "lifecycle_status,base_unit_id) VALUES (?,?,?,?,?,?,?)", args)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO products (id,code,name,name_normalized,product_type,"
                "lifecycle_status,base_unit_id) VALUES (?,?,?,?,?,?,?)",
                ("id2", "DUP", "N2", "n2", "RESALE_PRODUCT", "DRAFT", "u1"))

    def test_region_unique_per_species(self, conn):
        conn.execute("INSERT INTO species (id,code,name) VALUES ('s1','BOVINE','Bovino')")
        conn.execute("INSERT INTO anatomical_regions (id,species_id,code,name) "
                     "VALUES ('r1','s1','LOIN','Lomo')")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO anatomical_regions (id,species_id,code,name) "
                         "VALUES ('r2','s1','LOIN','Lomo dup')")
