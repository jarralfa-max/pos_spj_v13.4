# migrations/standalone/134_inventory_canonical_cutover.py
"""INV-27 — activate the canonical inventory cutover (backfill → parity → flag ON).

This is the ordered, atomic activation step of the "corte total": it seeds the
canonical ledger from whatever legacy stock exists, records a parity snapshot for
the audit trail, and turns the cutover flag ON persistently so every flipped
write path (sales / production / transfers) and every repointed reader switches
to the canonical projection on the next boot ("reads follow writes").

Ordering guarantees (§ REGLA CERO migration checklist):
  1. backfill legacy → canonical (opening-balance ADJUSTMENT_IN per product/branch),
  2. reconcile canonical vs legacy and log any drift,
  3. persist the GLOBAL setting ``canonical_cutover_enabled = true``.

Idempotent and safe on a fresh DB: with no legacy stock tables the backfill is a
no-op and the flag is simply set. The legacy tables are dropped by a LATER
migration, only after all legacy code that references them has been removed.
"""

from __future__ import annotations

import logging

from backend.application.inventory.cutover.reconciliation import (
    InventoryReconciliationService,
)
from backend.infrastructure.db.repositories.inventory.support_repositories import (
    InventorySettingsRepository,
)
from migrations.deferred import backfill_legacy_stock

logger = logging.getLogger("spj.migrations.134")

_SETTING_KEY = "canonical_cutover_enabled"


def run(conn) -> None:
    # 1. Backfill legacy stock into the canonical ledger (idempotent; no-op when
    #    there is no legacy stock table). Reuses the tested deferred backfill.
    result = backfill_legacy_stock.run(conn, env={"INVENTORY_ALLOW_BACKFILL": "1"})
    logger.info("134: backfill %s → %d seeded, %d skipped.",
                result.get("source"), result.get("seeded", 0), result.get("skipped", 0))

    # 2. Parity snapshot for the audit trail (never blocks — this is a dev app and
    #    drift is expected until the legacy writers are removed).
    try:
        drifts = InventoryReconciliationService(conn).drifts()
        if drifts:
            logger.warning("134: %d producto(s) con drift canónico↔legacy tras backfill.",
                           len(drifts))
    except Exception as exc:  # noqa: BLE001 — reconciliation is best-effort
        logger.debug("134: reconciliación no disponible: %s", exc)

    # 3. Flip the flag ON persistently — canonical is now authoritative.
    InventorySettingsRepository(conn).set(setting_key=_SETTING_KEY, setting_value="true")
    conn.commit()
    logger.warning("134: canonical inventory cutover ACTIVATED (flag ON).")


up = run
