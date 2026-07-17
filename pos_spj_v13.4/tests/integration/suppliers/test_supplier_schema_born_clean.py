"""FASE SUP-2 — the supplier schema is born-clean UUIDv7."""

import sqlite3

from backend.infrastructure.db.schema.supplier_schema import (
    SUPPLIER_TABLES,
    create_supplier_schema,
    drop_supplier_schema,
)


def test_all_tables_have_text_primary_key(sup_conn):
    for table in SUPPLIER_TABLES:
        info = sup_conn.execute(f"PRAGMA table_info({table})").fetchall()
        pk = [(r[1], r[2].upper()) for r in info if r[5] > 0]
        assert len(pk) == 1, f"{table} must have exactly one PK"
        name, col_type = pk[0]
        assert col_type == "TEXT", f"{table}.{name} PK must be TEXT, got {col_type}"


def test_no_integer_autoincrement_or_real_money(sup_conn):
    # money columns are TEXT, not REAL
    terms = {r[1]: r[2].upper() for r in
             sup_conn.execute("PRAGMA table_info(supplier_commercial_terms)").fetchall()}
    assert terms["credit_limit"] == "TEXT"
    assert terms["advance_percentage"] == "TEXT"
    products = {r[1]: r[2].upper() for r in
                sup_conn.execute("PRAGMA table_info(supplier_products)").fetchall()}
    assert products["last_cost"] == "TEXT" and products["current_cost"] == "TEXT"


def test_foreign_ids_are_text(sup_conn):
    contacts = {r[1]: r[2].upper() for r in
                sup_conn.execute("PRAGMA table_info(supplier_contacts)").fetchall()}
    assert contacts["supplier_id"] == "TEXT"


def test_indexes_exist(sup_conn):
    idx = {r[0] for r in sup_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index'").fetchall()}
    for expected in ("idx_supplier_master_tax", "idx_supplier_master_code",
                     "idx_supplier_master_name", "idx_supplier_master_status",
                     "idx_supplier_master_risk", "idx_supplier_master_rating"):
        assert expected in idx, f"missing index {expected}"


def test_create_is_idempotent(sup_conn):
    create_supplier_schema(sup_conn)  # second call must not raise


def test_supplier_code_is_unique(sup_conn):
    now = "2026-07-17T00:00:00"
    sup_conn.execute(
        "INSERT INTO supplier_master (id, supplier_code, legal_name, created_at, updated_at)"
        " VALUES ('a','PRV-000001','A', ?, ?)", (now, now))
    import pytest
    with pytest.raises(sqlite3.IntegrityError):
        sup_conn.execute(
            "INSERT INTO supplier_master (id, supplier_code, legal_name, created_at, updated_at)"
            " VALUES ('b','PRV-000001','B', ?, ?)", (now, now))


def test_drop_supplier_schema(sup_conn):
    dropped = drop_supplier_schema(sup_conn)
    assert set(dropped) == set(SUPPLIER_TABLES)
    remaining = {r[0] for r in sup_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert not (set(SUPPLIER_TABLES) & remaining)
