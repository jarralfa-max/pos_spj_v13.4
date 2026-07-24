"""PRC-3 — esquema born-clean de Pricing: UUIDv7, Money TEXT, sin REAL, idempotente."""

import sqlite3

import pytest

from backend.infrastructure.db.schema.pricing_schema import (
    PRICING_TABLES,
    create_pricing_schema,
    drop_pricing_schema,
)


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    create_pricing_schema(c)
    c.commit()
    yield c
    c.close()


def _cols(conn, table):
    return {r[1]: r[2] for r in conn.execute(f"PRAGMA table_info({table})")}


class TestShape:
    def test_all_tables(self, conn):
        rows = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for t in PRICING_TABLES:
            assert t in rows

    def test_pk_text(self, conn):
        assert _cols(conn, "product_price")["id"] == "TEXT"

    def test_no_real_columns(self, conn):
        for table in PRICING_TABLES:
            for r in conn.execute(f"PRAGMA table_info({table})"):
                assert r[2].upper() not in ("REAL", "FLOAT", "DOUBLE"), f"{table}.{r[1]}"

    def test_money_is_text(self, conn):
        pp = _cols(conn, "product_price")
        assert pp["sale_price"] == "TEXT" and pp["sale_price_currency"] == "TEXT"
        pc = _cols(conn, "product_cost")
        assert pc["average_cost"] == "TEXT"


class TestConstraints:
    def test_price_list_code_unique(self, conn):
        conn.execute("INSERT INTO price_list (id,code,name,kind) VALUES ('l1','BASE','B','BASE')")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO price_list (id,code,name,kind) VALUES ('l2','BASE','B2','BASE')")

    def test_product_price_unique_dimension(self, conn):
        conn.execute("INSERT INTO price_list (id,code,name,kind) VALUES ('l1','BASE','B','BASE')")
        conn.execute("INSERT INTO product_price (id,price_list_id,product_id,branch_id,"
                     "sale_price) VALUES ('pp1','l1','p1','','25.50')")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO product_price (id,price_list_id,product_id,branch_id,"
                         "sale_price) VALUES ('pp2','l1','p1','','30.00')")

    def test_product_cost_unique(self, conn):
        conn.execute("INSERT INTO product_cost (id,product_id,branch_id,average_cost) "
                     "VALUES ('c1','p1','','10.00')")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO product_cost (id,product_id,branch_id,average_cost) "
                         "VALUES ('c2','p1','','11.00')")


class TestIdempotency:
    def test_create_twice(self, conn):
        create_pricing_schema(conn)
        create_pricing_schema(conn)

    def test_drop_lists(self, conn):
        assert set(drop_pricing_schema(conn)) == set(PRICING_TABLES)
