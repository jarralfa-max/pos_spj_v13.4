#!/usr/bin/env python3
"""check_inventory_foreign_keys.py — CI guard for canonical inventory integrity (§7/§20).

Enables foreign-key enforcement and runs SQLite's ``PRAGMA foreign_key_check`` and
``PRAGMA integrity_check`` against the given database. Exits non-zero (failing CI) if
any foreign-key violation or corruption is found. With no ``--db`` it bootstraps a
fresh in-memory canonical inventory schema, so the check runs even without a DB file.

Usage:
    python scripts/check_inventory_foreign_keys.py [--db path/to/pos_spj.db]
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
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def check(conn: sqlite3.Connection) -> list[str]:
    problems: list[str] = []
    for row in conn.execute("PRAGMA foreign_key_check").fetchall():
        problems.append(f"FK violation: table={row[0]} rowid={row[1]} "
                        f"parent={row[2]} fkid={row[3]}")
    integrity = conn.execute("PRAGMA integrity_check").fetchall()
    if not (len(integrity) == 1 and integrity[0][0] == "ok"):
        problems.extend(f"integrity: {r[0]}" for r in integrity)
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=None, help="Ruta a la base (por defecto: esquema canónico en memoria)")
    args = parser.parse_args()
    conn = _connect(args.db)
    try:
        problems = check(conn)
    finally:
        conn.close()
    if problems:
        print("INVENTORY_FK_CHECK_FAILED")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("INVENTORY_FK_CHECK_OK (foreign_key_check + integrity_check limpios)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
