"""Helper compartido: DB SQLite en memoria born-clean (schema canónico m000)."""
from __future__ import annotations

import sqlite3


def make_db() -> sqlite3.Connection:
    import importlib

    from migrations import m000_base_schema as m000

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    m000.up(conn)
    # Migraciones canónicas que otras suites/servicios asumen presentes.
    # Se aplican en el mismo orden que migrations/engine.py.
    for module_name in (
        "migrations.standalone.057_loyalty_ledger_unificado",
        "migrations.standalone.082_treasury_tables",
        "migrations.standalone.083_financial_traceability_tables",
        "migrations.standalone.084_capital_movements",
        "migrations.standalone.092_loyalty_ledger_canonicalization",
        "migrations.standalone.098_canonical_inventory",
    ):
        module = importlib.import_module(module_name)
        run = getattr(module, "run", None) or getattr(module, "up", None)
        if run is not None:
            run(conn)
    return conn
