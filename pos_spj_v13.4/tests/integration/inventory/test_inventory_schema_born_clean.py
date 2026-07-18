"""INV-3 — the inventory schema is born-clean UUIDv7 + Decimal (no float identity)."""

import sqlite3

import pytest

from backend.infrastructure.db.schema.inventory_schema import (
    INVENTORY_TABLES,
    create_inventory_schema,
    drop_inventory_schema,
)
from backend.shared.ids import new_uuid


@pytest.fixture
def inv_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_inventory_schema(conn)
    yield conn
    conn.close()


def test_all_tables_created(inv_conn):
    names = {r[0] for r in inv_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    for table in INVENTORY_TABLES:
        assert table in names, f"falta tabla {table}"


def test_idempotent_creation(inv_conn):
    create_inventory_schema(inv_conn)  # a second create must not raise


def test_no_integer_primary_key_identity(inv_conn):
    for table in INVENTORY_TABLES:
        cols = inv_conn.execute(f"PRAGMA table_info({table})").fetchall()
        for col in [c for c in cols if c[5]]:  # c[5] = pk flag
            col_type = (col[2] or "").upper()
            assert "INT" not in col_type, (
                f"{table}.{col[1]} usa identidad entera ({col_type}); debe ser TEXT UUIDv7")


def test_quantity_weight_cost_columns_are_text(inv_conn):
    decimal_cols = {
        "inventory_ledger_lines": ("quantity", "weight", "unit_cost"),
        "inventory_balances": ("quantity", "weight", "reserved_quantity",
                               "reserved_weight"),
        "inventory_operation_limits": ("warning_threshold", "approval_threshold",
                                       "hard_cap"),
    }
    for table, columns in decimal_cols.items():
        info = {c[1]: (c[2] or "").upper()
                for c in inv_conn.execute(f"PRAGMA table_info({table})").fetchall()}
        for col in columns:
            assert info[col] == "TEXT", f"{table}.{col} debe ser TEXT (decimal), no REAL"


def test_no_real_columns_anywhere(inv_conn):
    for table in INVENTORY_TABLES:
        for c in inv_conn.execute(f"PRAGMA table_info({table})").fetchall():
            assert "REAL" not in (c[2] or "").upper(), (
                f"{table}.{c[1]} es REAL; prohibido (usar TEXT decimal)")


def test_movement_operation_id_unique(inv_conn):
    def _insert(mid, op):
        inv_conn.execute(
            "INSERT INTO inventory_ledger (id, movement_type, branch_id,"
            " warehouse_id, source_module, source_document_type, source_document_id,"
            " operation_id, created_by_user_id, occurred_at) VALUES"
            " (?,?,?,?,?,?,?,?,?,?)",
            (mid, "PURCHASE_RECEIPT", "b", "w", "procurement", "GOODS_RECEIPT",
             "gr1", op, "u1", "t"))
    _insert(new_uuid(), "op-1")
    with pytest.raises(sqlite3.IntegrityError):
        _insert(new_uuid(), "op-1")  # duplicate operation_id → idempotency guard


def test_balance_dimension_is_unique(inv_conn):
    def _insert(bid):
        inv_conn.execute(
            "INSERT INTO inventory_balances (id, product_id, branch_id, warehouse_id,"
            " location_id, lot_id, serial_id, inventory_status, quantity, weight,"
            " reserved_quantity, reserved_weight, updated_at) VALUES"
            " (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (bid, "p1", "b1", "w1", "", "", "", "AVAILABLE", "0", "0", "0", "0", "t"))
    _insert(new_uuid())
    with pytest.raises(sqlite3.IntegrityError):
        _insert(new_uuid())  # same full dimension → one balance row only


def test_ledger_to_balance_smoke(inv_conn):
    """A movement + its line + the projected balance persist and read back as Decimal strings."""
    mv_id, line_id, bal_id = new_uuid(), new_uuid(), new_uuid()
    inv_conn.execute(
        "INSERT INTO inventory_ledger (id, movement_type, branch_id, warehouse_id,"
        " source_module, source_document_type, source_document_id, operation_id,"
        " created_by_user_id, occurred_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (mv_id, "PURCHASE_RECEIPT", "b1", "w1", "procurement", "GOODS_RECEIPT",
         "gr1", "op-1", "u1", "t"))
    inv_conn.execute(
        "INSERT INTO inventory_ledger_lines (id, movement_id, product_id, quantity,"
        " weight, unit, to_location_id) VALUES (?,?,?,?,?,?,?)",
        (line_id, mv_id, "p1", "25", "58.750", "KG", "loc1"))
    inv_conn.execute(
        "INSERT INTO inventory_balances (id, product_id, branch_id, warehouse_id,"
        " location_id, lot_id, serial_id, inventory_status, quantity, weight,"
        " reserved_quantity, reserved_weight, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (bal_id, "p1", "b1", "w1", "loc1", "", "", "AVAILABLE", "25", "58.750",
         "0", "0", "t"))
    inv_conn.commit()
    row = inv_conn.execute(
        "SELECT quantity, weight FROM inventory_balances WHERE id=?", (bal_id,)).fetchone()
    assert row["quantity"] == "25" and row["weight"] == "58.750"


def test_drop_schema(inv_conn):
    dropped = drop_inventory_schema(inv_conn)
    assert set(dropped) == set(INVENTORY_TABLES)
    names = {r[0] for r in inv_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert not (set(INVENTORY_TABLES) & names)
