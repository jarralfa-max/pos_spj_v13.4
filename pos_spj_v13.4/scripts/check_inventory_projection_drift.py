#!/usr/bin/env python3
"""check_inventory_projection_drift.py — CI guard for balance drift (§6.3/§20).

Rebuilds the balance projection from the ledger and diffs it against the live
``inventory_balances``. Exits non-zero (failing CI / aborting a cutover) if any
per-dimension quantity/weight drift is found. With no ``--db`` it bootstraps a
fresh in-memory canonical schema (trivially zero drift).

Usage:
    python scripts/check_inventory_projection_drift.py [--db path/to/pos_spj.db]
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _connect(db_path: str | None) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path or ":memory:")
    conn.row_factory = sqlite3.Row
    if not db_path:
        from backend.infrastructure.db.schema.inventory_schema import (
            create_inventory_schema,
        )
        create_inventory_schema(conn)
        conn.commit()
    return conn


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=None, help="Ruta a la base (por defecto: esquema canónico en memoria)")
    args = parser.parse_args()
    from backend.application.inventory.use_cases.rebuild_inventory_balances import (
        ValidateInventoryProjectionUseCase,
    )
    conn = _connect(args.db)
    try:
        drifts = ValidateInventoryProjectionUseCase(conn).validate()
    finally:
        conn.close()
    if drifts:
        print("INVENTORY_PROJECTION_DRIFT_DETECTED")
        for d in drifts:
            print(f"  - key={d.key} qty {d.projected_quantity}!={d.rebuilt_quantity} "
                  f"(drift {d.quantity_drift}); weight {d.projected_weight}!="
                  f"{d.rebuilt_weight}")
        return 1
    print("INVENTORY_PROJECTION_OK (cero drift ledger↔balances)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
