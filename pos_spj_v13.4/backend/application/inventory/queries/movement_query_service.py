"""MovementQueryService — the read the Movimientos UI consults (§15).

Read-only projection over ``inventory_ledger``: lists recent posted movements
(most recent first, bounded) for display — date, type, source module/document and
status. It never writes; movements are appended only by the posting use cases.
"""

from __future__ import annotations

from backend.infrastructure.db.repositories.inventory.base import (
    InventoryRepositoryBase,
    zn,
)


class MovementQueryService(InventoryRepositoryBase):
    def list_recent(self, *, branch_id: str | None = None,
                    limit: int = 100) -> list[dict]:
        """Recent ledger movements (most recent first), optionally scoped to a
        branch and bounded by ``limit`` so the UI never pulls the whole ledger."""
        cols = ("id, movement_type, branch_id, warehouse_id, source_module,"
                " source_document_type, source_document_id, status, occurred_at")
        lim = max(1, int(limit))
        if branch_id:
            rows = self._query(
                f"SELECT {cols} FROM inventory_ledger WHERE branch_id=?"
                " ORDER BY occurred_at DESC, id DESC LIMIT ?", (branch_id, lim))
        else:
            rows = self._query(
                f"SELECT {cols} FROM inventory_ledger"
                " ORDER BY occurred_at DESC, id DESC LIMIT ?", (lim,))
        return [dict(r) | {"source_document_id": zn(r["source_document_id"])}
                for r in rows]
