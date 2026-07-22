"""Inventory legacy→canonical cutover (INV-27), flag-gated.

The canonical inventory context has been built strictly in parallel: its handlers
post to the born-clean ledger but are NOT wired to the live EventBus, so the
legacy stock path keeps owning stock and nothing double-counts. This package
holds the *controlled flip*:

- ``is_cutover_enabled`` — the feature flag (env or inventory_settings), OFF by
  default; while OFF, nothing here changes runtime behavior.
- ``CanonicalInventoryCutover`` — when the flag is ON, subscribes the canonical
  handlers to the live events and neutralizes the legacy handlers.
- ``InventoryReconciliationService`` — compares canonical balances vs legacy
  stock so parity can be verified BEFORE flipping.

Dropping the legacy tables is deliberately NOT done here: it lives in a deferred,
env-guarded migration (``migrations/deferred/legacy_inventory_drop.py``) that
never runs automatically, because live readers must be repointed first.
"""

from backend.application.inventory.cutover.canonical_cutover import (
    CanonicalInventoryCutover,
    is_cutover_enabled,
)
from backend.application.inventory.cutover.reconciliation import (
    InventoryReconciliationService,
    ReconciliationRow,
)

__all__ = [
    "CanonicalInventoryCutover",
    "InventoryReconciliationService",
    "ReconciliationRow",
    "is_cutover_enabled",
]
