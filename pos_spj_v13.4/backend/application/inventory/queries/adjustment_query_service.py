"""AdjustmentQueryService — the read the Inventario «Ajustes» UI consults (§14).

Read-only projection over ``inventory_adjustment``: lists recent adjustments per
branch — folio, reason, warehouse and status — most recent first, bounded. It
never writes; adjustments are created, approved and posted by the adjustment use
cases.
"""

from __future__ import annotations

from backend.infrastructure.db.repositories.inventory.base import (
    InventoryRepositoryBase,
)


class AdjustmentQueryService(InventoryRepositoryBase):
    def list_recent(self, *, branch_id: str | None = None,
                    limit: int = 200) -> list[dict]:
        """Recent adjustments (most recent first, bounded), optionally scoped to a
        branch. Rows carry id, folio, reason, warehouse and status."""
        cols = ("id, folio, reason, warehouse_id, status, created_at")
        lim = max(1, int(limit))
        if branch_id:
            rows = self._query(
                f"SELECT {cols} FROM inventory_adjustment WHERE branch_id=?"
                " ORDER BY created_at DESC, id DESC LIMIT ?", (branch_id, lim))
        else:
            rows = self._query(
                f"SELECT {cols} FROM inventory_adjustment"
                " ORDER BY created_at DESC, id DESC LIMIT ?", (lim,))
        return [{
            "id": r["id"], "folio": r["folio"], "reason": r["reason"],
            "warehouse_id": r["warehouse_id"], "status": r["status"],
            "created_at": r["created_at"],
        } for r in rows]
