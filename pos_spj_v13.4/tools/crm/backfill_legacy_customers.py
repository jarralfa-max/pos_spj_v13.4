"""
backfill_legacy_customers.py — pos_spj v13.4 (CRM-21)

One-time/resumable CLI to bridge every `clientes` row to a `customers` row
(`customers.legacy_customer_id`, migration 193) via
`BackfillLegacyCustomersUseCase`. Safe to re-run: already-bridged rows are
skipped (`WHERE legacy_customer_id IS NOT NULL`).

Usage:
    python tools/crm/backfill_legacy_customers.py --db pos_spj.db
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.application.customers.use_cases.legacy_customer_bridge_use_cases import (
    BackfillLegacyCustomersUseCase,
)


def run(db_path: str, *, batch_size: int = 500) -> int:
    conn = sqlite3.connect(db_path)
    use_case = BackfillLegacyCustomersUseCase()
    total_created = 0
    try:
        while True:
            result = use_case.execute(conn, batch_size=batch_size)
            total_created += result["created"]
            print(f"Lote: {result['created']} clientes puenteados, "
                  f"{result['remaining']} restantes.")
            if result["created"] == 0:
                break
        conn.commit()
    finally:
        conn.close()
    print(f"Listo: {total_created} clientes puenteados en total.")
    return total_created


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="Ruta a la base de datos SQLite")
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args()
    run(args.db, batch_size=args.batch_size)


if __name__ == "__main__":
    main()
