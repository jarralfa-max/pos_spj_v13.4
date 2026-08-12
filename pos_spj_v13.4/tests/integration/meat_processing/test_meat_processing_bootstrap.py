"""PROC-3: meat_processing schema must come up clean through the real bootstrap
path (migrations.engine.up), not just when its own migration module is imported
directly."""

import sqlite3

from migrations.engine import MIGRATIONS, up


def test_migration_187_is_registered_in_strict_order():
    versions = [migration.version for migration in MIGRATIONS]
    assert "187" in versions
    assert versions.index("187") > versions.index("186")


def test_full_bootstrap_includes_meat_processing_schema():
    conn = sqlite3.connect(":memory:")
    up(conn)
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {
        "processing_orders", "processing_batches", "process_executions",
        "material_consumptions", "process_outputs", "process_weighings",
        "yield_reconciliations", "meat_processing_outbox",
        "meat_processing_processed_events",
    } <= tables
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    conn.close()


def test_bootstrap_is_idempotent_for_meat_processing_schema():
    conn = sqlite3.connect(":memory:")
    up(conn)
    up(conn)  # second run must not fail or duplicate
    version_count = conn.execute(
        "SELECT COUNT(*) FROM schema_migrations WHERE version='187'").fetchone()[0]
    assert version_count == 1
    conn.close()
