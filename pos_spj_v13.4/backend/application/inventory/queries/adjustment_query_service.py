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
    def list_recent(self, *, branch_id: str | None = None, reason: str | None = None,
                    limit: int = 200) -> list[dict]:
        """Recent adjustments (most recent first, bounded), optionally scoped to a
        branch and/or a reason (§28 "Ver historial" — e.g. ``WEIGHT_VARIANCE`` for
        catch-weight captures). Rows carry id, folio, reason, warehouse and status."""
        cols = ("id, folio, reason, warehouse_id, status, created_at")
        lim = max(1, int(limit))
        where = []
        params: tuple = ()
        if branch_id:
            where.append("branch_id=?")
            params += (branch_id,)
        if reason:
            where.append("reason=?")
            params += (reason,)
        clause = f" WHERE {' AND '.join(where)}" if where else ""
        rows = self._query(
            f"SELECT {cols} FROM inventory_adjustment{clause}"
            " ORDER BY created_at DESC, id DESC LIMIT ?", params + (lim,))
        return [{
            "id": r["id"], "folio": r["folio"], "reason": r["reason"],
            "warehouse_id": r["warehouse_id"], "status": r["status"],
            "created_at": r["created_at"],
        } for r in rows]
