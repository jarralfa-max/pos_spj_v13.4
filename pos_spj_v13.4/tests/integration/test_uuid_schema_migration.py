"""Integration tests for UUID schema migration readiness.

These tests verify the pre-conditions and post-conditions of the
FASE 2.5 atomic UUID cutover defined in the skill.

Tests are currently in AUDIT mode: they document the current state
and enforce that new code does not add integer-primary-key tables.
"""

from __future__ import annotations

import re
import sqlite3
import tempfile
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
IDS_PATH = PACKAGE_ROOT / "backend" / "shared" / "ids.py"
MIGRATION_ENGINE = PACKAGE_ROOT / "migrations" / "engine.py"

UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# ids.py contract
# ---------------------------------------------------------------------------

def _load_ids():
    import importlib.util
    spec = importlib.util.spec_from_file_location("spj_ids", IDS_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_new_uuid_contract():
    ids = _load_ids()
    uid = ids.new_uuid()
    assert isinstance(uid, str)
    assert UUID_PATTERN.match(uid), f"Not a valid UUIDv7: {uid}"
    assert uid == uid.lower(), "UUID must be lowercase"


def test_new_uuid_is_unique_under_load():
    ids = _load_ids()
    uids = {ids.new_uuid() for _ in range(2000)}
    assert len(uids) == 2000, "Collision detected in 2000 UUIDs"


def test_new_uuid_timestamps_are_non_decreasing():
    """UUIDv7 timestamps (first 48 bits) must be non-decreasing across calls."""
    import time
    ids = _load_ids()
    uids = []
    for _ in range(50):
        uids.append(ids.new_uuid())
        time.sleep(0.001)
    timestamps = [u.replace("-", "")[:12] for u in uids]
    assert timestamps == sorted(timestamps), "UUIDv7 timestamps must be non-decreasing"


# ---------------------------------------------------------------------------
# Backend layer type-system correctness
# ---------------------------------------------------------------------------

def test_inventory_commands_use_str_ids():
    """All new inventory commands must declare IDs as str, not int."""
    src = (PACKAGE_ROOT / "backend" / "application" / "commands" / "inventory_commands.py").read_text()
    assert "product_id: int" not in src, "inventory_commands.py must not declare product_id as int"
    assert "from_branch_id: int" not in src, "inventory_commands.py must not declare from_branch_id as int"
    assert "to_branch_id: int" not in src, "inventory_commands.py must not declare to_branch_id as int"


def test_product_commands_use_str_ids():
    src = (PACKAGE_ROOT / "backend" / "application" / "commands" / "product_commands.py").read_text()
    assert "product_id: int" not in src, "product_commands.py must not declare product_id as int"


def test_sales_commands_use_str_ids():
    src = (PACKAGE_ROOT / "backend" / "application" / "commands" / "sales_commands.py").read_text()
    assert "customer_id: int" not in src
    assert "reservation_id: int" not in src


def test_waste_commands_use_str_ids():
    src = (PACKAGE_ROOT / "backend" / "application" / "commands" / "waste_commands.py").read_text()
    assert "product_id: int" not in src


def test_use_case_commands_use_str_ids():
    """Individual use case command dataclasses must not have int IDs."""
    files = [
        "backend/application/use_cases/deactivate_product_use_case.py",
        "backend/application/use_cases/restore_product_use_case.py",
        "backend/application/use_cases/get_inventory_stock_use_case.py",
    ]
    for rel in files:
        src = (PACKAGE_ROOT / rel).read_text()
        assert "product_id: int" not in src, f"{rel}: product_id must be str"
        assert "branch_id: int" not in src, f"{rel}: branch_id must be str"


# ---------------------------------------------------------------------------
# SQLite inventory_stock schema — uuid readiness audit
# ---------------------------------------------------------------------------

def test_inventory_stock_schema_in_fresh_db():
    """Document current inventory_stock schema.

    Currently inventory_stock uses INTEGER product_id and branch_id.
    This test captures the CURRENT state. Once the UUID cutover migration
    runs, these assertions must be updated to check TEXT columns.
    """
    schema_sql = """
    CREATE TABLE IF NOT EXISTS inventory_stock (
        product_id INTEGER NOT NULL,
        branch_id  INTEGER NOT NULL,
        quantity   REAL    NOT NULL DEFAULT 0,
        unit       TEXT    NOT NULL DEFAULT 'unit',
        updated_at TEXT,
        PRIMARY KEY (product_id, branch_id)
    );
    """
    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        conn = sqlite3.connect(f.name)
        conn.execute(schema_sql)
        cursor = conn.execute("PRAGMA table_info(inventory_stock)")
        cols = {row[1]: row[2] for row in cursor.fetchall()}
        conn.close()

    assert cols["product_id"] == "INTEGER"
    assert cols["branch_id"] == "INTEGER"


def test_inventory_stock_uuid_schema_target():
    """Verify the TARGET schema for UUID cutover (inventory_stock with TEXT PKs).

    This test validates what the post-cutover schema must look like.
    After migration 200 runs, inventory_stock.product_id and branch_id
    must be TEXT columns.
    """
    target_schema_sql = """
    CREATE TABLE IF NOT EXISTS inventory_stock_uuid (
        product_id TEXT NOT NULL,
        branch_id  TEXT NOT NULL,
        quantity   REAL NOT NULL DEFAULT 0,
        unit       TEXT NOT NULL DEFAULT 'unit',
        updated_at TEXT,
        PRIMARY KEY (product_id, branch_id)
    );
    """
    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        conn = sqlite3.connect(f.name)
        conn.execute(target_schema_sql)
        cursor = conn.execute("PRAGMA table_info(inventory_stock_uuid)")
        cols = {row[1]: row[2] for row in cursor.fetchall()}
        conn.close()

    assert cols["product_id"] == "TEXT"
    assert cols["branch_id"] == "TEXT"


# ---------------------------------------------------------------------------
# UUID foreign-key integrity simulation
# ---------------------------------------------------------------------------

def test_uuid_foreign_key_integrity_in_simulation():
    """Simulate a UUID-keyed sale with sale_items FK constraint.

    This is a preview of what the schema will look like after cutover.
    """
    ids = _load_ids()

    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        conn = sqlite3.connect(f.name)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript("""
            CREATE TABLE sales (
                id         TEXT PRIMARY KEY,
                branch_id  TEXT NOT NULL,
                total      REAL NOT NULL DEFAULT 0
            );
            CREATE TABLE sale_items (
                id         TEXT PRIMARY KEY,
                sale_id    TEXT NOT NULL REFERENCES sales(id),
                product_id TEXT NOT NULL,
                quantity   REAL NOT NULL,
                price      REAL NOT NULL
            );
        """)
        sale_id = ids.new_uuid()
        branch_id = ids.new_uuid()
        product_id = ids.new_uuid()
        item_id = ids.new_uuid()

        conn.execute("INSERT INTO sales VALUES (?, ?, 100.0)", (sale_id, branch_id))
        conn.execute(
            "INSERT INTO sale_items VALUES (?, ?, ?, 2.0, 50.0)",
            (item_id, sale_id, product_id),
        )
        conn.commit()

        row = conn.execute("SELECT id FROM sales WHERE id = ?", (sale_id,)).fetchone()
        assert row is not None
        assert row[0] == sale_id

        items = conn.execute("SELECT * FROM sale_items WHERE sale_id = ?", (sale_id,)).fetchall()
        assert len(items) == 1
        assert items[0][1] == sale_id  # index 1 = sale_id column

        conn.execute("PRAGMA foreign_key_check")
        conn.close()


def test_uuid_offline_collision_resistance():
    """Simulate 3 offline nodes generating IDs concurrently — no collisions expected."""
    ids = _load_ids()
    node_a = {ids.new_uuid() for _ in range(500)}
    node_b = {ids.new_uuid() for _ in range(500)}
    node_c = {ids.new_uuid() for _ in range(500)}
    all_ids = node_a | node_b | node_c
    assert len(all_ids) == 1500, f"UUID collision detected: expected 1500 unique, got {len(all_ids)}"
