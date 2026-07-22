# migrations/deferred/backfill_legacy_stock.py
"""DEFERRED, ENV-GUARDED backfill of legacy stock into the canonical ledger (INV-27).

Prerequisite for repointing any legacy read to the canonical projection: today
``inventory_balances`` is empty (canonical handlers aren't live-wired yet), while
the real stock lives in the legacy ``inventario_actual`` / ``inventory_stock``
tables. This one-time backfill seeds the canonical ledger with an opening-balance
``ADJUSTMENT_IN`` movement per legacy (product, branch) row, which projects into
``inventory_balances`` — keeping the ledger-first invariant (the balance is always
a projection of the ledger, never seeded directly).

NOT registered in engine.py; runs only when invoked explicitly and only with
``INVENTORY_ALLOW_BACKFILL=1``. Idempotent: each source row maps to a stable
``operation_id`` so a re-run is a no-op (PostInventoryMovementUseCase dedupes).
Branch maps to warehouse (warehouse_id = branch_id), status AVAILABLE — the same
convention the canonical handlers use when no explicit warehouse is given.
"""

from __future__ import annotations

import logging
import os
from decimal import Decimal

from backend.application.inventory.use_cases.post_inventory_movement import (
    PostInventoryMovementUseCase,
)
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.enums import MovementType

logger = logging.getLogger("spj.migrations.backfill_legacy_stock")

_ENV_GUARD = "INVENTORY_ALLOW_BACKFILL"

# (table, product_col, branch_col, qty_col) in priority order; first present wins.
_LEGACY_SOURCES = (
    ("inventario_actual", "producto_id", "sucursal_id", "cantidad"),
    ("inventory_stock", "product_id", "branch_id", "quantity"),
)


def _table_exists(conn, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _quantize(value) -> Decimal:
    """Legacy REAL → Decimal, without a float() coercion, quantized to 6 places."""
    if value in (None, ""):
        return Decimal("0")
    return Decimal(str(value)).quantize(Decimal("0.000001"))


def run(conn, *, env=None) -> dict:
    env = os.environ if env is None else env
    if str(env.get(_ENV_GUARD, "")).strip() != "1":
        raise RuntimeError(
            "Backfill de stock legacy bloqueado: exporta "
            f"{_ENV_GUARD}=1 para ejecutarlo.")

    source = next((s for s in _LEGACY_SOURCES if _table_exists(conn, s[0])), None)
    if source is None:
        logger.info("Backfill: no hay tabla de stock legacy; nada que migrar.")
        return {"source": None, "seeded": 0, "skipped": 0}

    table, prod_col, branch_col, qty_col = source
    use_case = PostInventoryMovementUseCase()
    rows = conn.execute(
        f"SELECT {prod_col} AS p, {branch_col} AS b, {qty_col} AS q FROM {table}"
    ).fetchall()

    seeded = skipped = 0
    for row in rows:
        product_id = str(row["p"] if hasattr(row, "keys") else row[0])
        branch_id = str(row["b"] if hasattr(row, "keys") else row[1])
        qty = _quantize(row["q"] if hasattr(row, "keys") else row[2])
        if not product_id or not branch_id or qty <= 0:
            skipped += 1
            continue
        operation_id = f"backfill:{table}:{product_id}:{branch_id}"
        line = InventoryMovementLine.create(
            product_id=product_id, quantity=qty, to_location_id=branch_id,
            reason_code="OPENING_BALANCE_BACKFILL")
        movement = InventoryMovement.create(
            movement_type=MovementType.ADJUSTMENT_IN, branch_id=branch_id,
            warehouse_id=branch_id, source_module="migration",
            source_document_type="LEGACY_BACKFILL", source_document_id=table,
            operation_id=operation_id, created_by_user_id="system", lines=[line])
        result = use_case.execute(conn, movement, actor_user_id="system")
        if result.success and not result.data.get("already_processed"):
            seeded += 1
        elif result.success:
            skipped += 1  # idempotent replay — already seeded
        else:
            skipped += 1
            logger.warning("Backfill %s falló: %s", operation_id, result.message)

    conn.commit()
    logger.warning("Backfill legacy→canónico: %d sembrados, %d omitidos (fuente %s).",
                   seeded, skipped, table)
    return {"source": table, "seeded": seeded, "skipped": skipped}


up = run
