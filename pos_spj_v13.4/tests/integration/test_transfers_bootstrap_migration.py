import sqlite3
from importlib import import_module

from migrations.engine import MIGRATIONS


def test_transfers_schema_migration_is_registered_and_bootstraps_cleanly():
    assert any(m.version == "154" and m.module.endswith("154_transfers_bounded_context_schema") for m in MIGRATIONS)
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    import_module("migrations.standalone.154_transfers_bounded_context_schema").run(connection)
    assert connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='stock_transfers'").fetchone()
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
