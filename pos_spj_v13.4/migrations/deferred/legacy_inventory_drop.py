# migrations/deferred/legacy_inventory_drop.py
"""DEFERRED, ENV-GUARDED drop of the legacy inventory tables (INV-27).

This is NOT registered in migrations/engine.py and never runs automatically.
Run it manually ONLY after:
  1. the canonical cutover flag is ON and canonical handlers own stock,
  2. every legacy operational read has been repointed to the canonical
     projection (InventoryAvailabilityQueryService / inventory_balances), and
  3. InventoryReconciliationService reports parity.

Because it destroys data with (historically) live readers, it refuses to run
unless ``INVENTORY_ALLOW_LEGACY_DROP=1`` is set. Uses DROP TABLE IF EXISTS so a
partial legacy schema is fine.

Reclaiming the canonical name ``inventory_movements`` (rename inventory_ledger →
inventory_movements) is intentionally left as a separate follow-up rename step so
the canonical code keeps working until every reference is updated.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("spj.migrations.legacy_inventory_drop")

_ENV_GUARD = "INVENTORY_ALLOW_LEGACY_DROP"

# Legacy stock sources, ledgers, transfers, reservations, lots (consolidation map).
LEGACY_TABLES = (
    "inventario_actual", "inventory_stock", "branch_inventory",
    "inventario_diario", "inventario_global", "inventario_subproductos",
    "inventario_sucursal",
    "inventory_movements", "movimientos_inventario", "movimientos_lote",
    "movimientos_trazabilidad",
    "transferencias", "transferencias_inventario", "traspasos", "recepciones",
    "ajustes_inventario",
    "stock_reservas", "stock_reservas_detalle", "inventory_reservations",
    "lotes",
)

# Legacy triggers that sync the deprecated productos.existencia column and the
# buggy inventario_actual recalc.
LEGACY_TRIGGERS = (
    "trg_sync_existencia_insert", "trg_sync_existencia_update",
    "trg_sync_existencia_delete", "trg_recalc_inventario_actual",
)


def run(conn, *, env=None) -> dict:
    env = os.environ if env is None else env
    if str(env.get(_ENV_GUARD, "")).strip() != "1":
        raise RuntimeError(
            "Drop de inventario legacy bloqueado: exporta "
            f"{_ENV_GUARD}=1 para ejecutarlo (sólo tras repuntar lectores y "
            "verificar paridad con InventoryReconciliationService).")

    dropped, dropped_triggers = [], []
    for trigger in LEGACY_TRIGGERS:
        conn.execute(f"DROP TRIGGER IF EXISTS {trigger}")
        dropped_triggers.append(trigger)
    for table in LEGACY_TABLES:
        conn.execute(f"DROP TABLE IF EXISTS {table}")
        dropped.append(table)
    conn.commit()
    logger.warning("Legacy inventory DROP done: %d tables, %d triggers.",
                   len(dropped), len(dropped_triggers))
    return {"tables": dropped, "triggers": dropped_triggers}


up = run
