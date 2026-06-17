"""FASE 2.5 — UUID-only schema cutover (atomic migration).

This migration converts all functional entity primary keys and foreign keys
from INTEGER to TEXT (UUIDv7). It is designed as an atomic, all-or-nothing
operation with automatic backup and rollback on failure.

STATUS: SKELETON — NOT YET EXECUTABLE.
This file documents the required steps and the target schema.
It must be completed and reviewed before being added to MIGRATIONS in engine.py.

PREREQUISITES:
  - All application code must use backend.shared.ids.new_uuid() for IDs.
  - No callers may pass int IDs to any use case, command, or repository.
  - run() must be invoked with the application shut down and locked.
  - A full SQLite backup must exist before calling run().

TABLES TO MIGRATE (add more as discovered):
  productos, clientes, sucursales, usuarios, roles, permisos_roles,
  ventas, detalle_ventas, pagos, cajas, cortes_caja, movimientos_caja,
  inventory_stock, inventory_movements, stock_reservations, stock_reservation_items,
  mermas, recetas, componentes_recetas, producciones, lotes,
  compras, detalle_compras, ordenes_compra, recepciones_compra,
  transferencias, detalle_transferencias, cotizaciones, detalle_cotizaciones,
  pedidos, detalle_pedidos, delivery_orders, empleados, nomina, activos,
  mantenimientos, tarjetas_fidelidad, puntos_fidelidad, notificaciones,
  event_outbox, audit_log, print_jobs.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MIGRATION_VERSION = 200
MIGRATION_NAME = "uuid_only_schema_cutover"

# ---------------------------------------------------------------------------
# Sentinel: this migration is NOT ready to run.
# Remove this constant once the full implementation is verified.
# ---------------------------------------------------------------------------
_NOT_READY = True


def run(conn: Any) -> None:
    """Entry point called by migrations/engine.py.

    Raises NotImplementedError until the full implementation is complete.
    """
    if _NOT_READY:
        raise NotImplementedError(
            "Migration 200 (UUID cutover) is not yet implemented. "
            "Complete the FASE 2.5 cutover plan before enabling this migration."
        )
    _execute(conn)


def _execute(conn: Any) -> None:
    """Atomic UUID cutover — to be implemented.

    Steps (per FASE 2.5 skill spec):
      1. Verify application is shut down (external responsibility).
      2. Create and verify full SQLite backup.
      3. Open exclusive transaction.
      4. Audit all tables for INTEGER PKs and FKs.
      5. Create uuid_id_map: { table: { old_int_id: new_uuid } }.
      6. For each table:
           a. Create new_<table> with TEXT PK/FKs.
           b. Populate using uuid_id_map for all ID columns.
           c. Validate row counts match.
      7. Drop old tables.
      8. Rename new_<table> → <table>.
      9. Recreate indexes, triggers, unique constraints.
      10. PRAGMA foreign_key_check — must return no rows.
      11. Commit.
      12. Drop uuid_id_map from memory (never persist it).
      13. Block application start if any INTEGER PK remains.
    """
    raise NotImplementedError("_execute not yet implemented")


# ---------------------------------------------------------------------------
# Helper: audit current schema for remaining INTEGER PKs
# ---------------------------------------------------------------------------

def audit_integer_pks(conn: Any) -> dict[str, list[str]]:
    """Return {table_name: [column_names]} for all INTEGER PRIMARY KEY columns."""
    violations: dict[str, list[str]] = {}
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    for (table,) in cursor.fetchall():
        if table.startswith("sqlite_") or table.startswith("schema_"):
            continue
        col_cursor = conn.execute(f"PRAGMA table_info({table})")
        for row in col_cursor.fetchall():
            col_name, col_type, pk = row[1], row[2], row[5]
            if pk and col_type.upper() in ("INTEGER", "INT"):
                violations.setdefault(table, []).append(col_name)
    return violations
