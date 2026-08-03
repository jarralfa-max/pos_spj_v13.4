"""CountQueryService — the read the Inventario «Conteos» UI consults (§17).

Read-only projection over ``inventory_count``: lists recent stock counts (cyclic,
full, spot…) per branch — folio, type, warehouse, blind flag and status — most
recent first, bounded. It never writes; counts are created and progressed by the
count use cases.
"""

from __future__ import annotations

from backend.infrastructure.db.repositories.inventory.base import (
    InventoryRepositoryBase,
)


class CountQueryService(InventoryRepositoryBase):
    def list_recent(self, *, branch_id: str | None = None,
                    limit: int = 200) -> list[dict]:
        """Recent counts (most recent first, bounded), optionally scoped to a
        branch. Rows carry folio, type, warehouse, blind flag and status."""
        cols = ("folio, count_type, warehouse_id, blind, status, created_at")
        lim = max(1, int(limit))
        if branch_id:
            rows = self._query(
                f"SELECT {cols} FROM inventory_count WHERE branch_id=?"
                " ORDER BY created_at DESC, id DESC LIMIT ?", (branch_id, lim))
        else:
            rows = self._query(
                f"SELECT {cols} FROM inventory_count"
                " ORDER BY created_at DESC, id DESC LIMIT ?", (lim,))
        return [{
            "folio": r["folio"], "count_type": r["count_type"],
            "warehouse_id": r["warehouse_id"], "blind": bool(r["blind"]),
            "status": r["status"], "created_at": r["created_at"],
        } for r in rows]
