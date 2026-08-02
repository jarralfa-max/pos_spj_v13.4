"""P0-B (§7) — referential integrity of the canonical inventory schema.

The born-clean schema declares foreign keys + UNIQUE(operation_id)/UNIQUE(event_id);
these tests prove enforcement is real (with foreign_keys=ON) and that the CI check
scripts pass on a fresh canonical DB. FK enforcement must never be disabled in tests.
"""

import sqlite3

import pytest

from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from backend.shared.ids import new_uuid


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_inventory_schema(c)
    c.execute("PRAGMA foreign_keys=ON")
    c.commit()
    yield c
    c.close()


def test_foreign_key_and_integrity_check_are_clean(conn):
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_ledger_line_requires_existing_movement(conn):
    # A ledger line pointing at a non-existent movement must be rejected by the FK.
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO inventory_ledger_lines (id, movement_id, product_id,"
            " quantity, weight, unit) VALUES (?,?,?,?,?,?)",
            (new_uuid(), new_uuid(), "p1", "1", "0", "PZA"))
        conn.commit()


def test_operation_id_is_unique_on_ledger(conn):
    op = new_uuid()

    def _insert_movement():
        conn.execute(
            "INSERT INTO inventory_ledger (id, movement_type, branch_id, warehouse_id,"
            " source_module, source_document_type, source_document_id, operation_id,"
            " created_by_user_id, status, occurred_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,datetime('now'))",
            (new_uuid(), "PURCHASE_RECEIPT", "b1", "w1", "procurement", "GR", "gr1",
             op, "u1", "POSTED"))

    _insert_movement()
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        _insert_movement()
        conn.commit()


def test_check_scripts_pass_on_fresh_schema():
    from scripts.check_inventory_foreign_keys import check
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_inventory_schema(c)
    c.execute("PRAGMA foreign_keys=ON")
    assert check(c) == []
    c.close()
