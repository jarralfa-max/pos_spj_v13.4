"""Helper compartido: DB SQLite en memoria born-clean (schema canónico m000)."""
from __future__ import annotations

import sqlite3


def make_db() -> sqlite3.Connection:
    import importlib

    from migrations import m000_base_schema as m000

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    m000.up(conn)
    # Inventario canónico (inventory_stock / inventory_movements) — misma
    # migración registrada en migrations/engine.py.
    inv = importlib.import_module("migrations.standalone.098_canonical_inventory")
    inv.run(conn)
    return conn
