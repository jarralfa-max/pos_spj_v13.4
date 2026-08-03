"""TransferQueryService — the read the Inventario «Transferencias» UI consults.

Read-only window over the canonical ``stock_transfers`` table (owned by the
Transfers bounded context): lists recent physical transfers that touch a branch —
as origin or destination — most recent first, bounded. It never writes; the whole
transfer lifecycle (request → dispatch → receipt) lives in the Transfers module.
The inventory section only surfaces the activity.
"""

from __future__ import annotations

from backend.infrastructure.db.repositories.inventory.base import (
    InventoryRepositoryBase,
    zn,
)


class TransferQueryService(InventoryRepositoryBase):
    def list_recent(self, *, branch_id: str | None = None,
                    limit: int = 200) -> list[dict]:
        """Recent transfers (most recent first, bounded). When ``branch_id`` is
        given, only transfers whose origin or destination branch matches are
        returned, so a sucursal sees just its own movement of stock."""
        cols = ("transfer_number, transfer_type, origin_branch_id,"
                " destination_branch_id, status, updated_at")
        lim = max(1, int(limit))
        if branch_id:
            rows = self._query(
                f"SELECT {cols} FROM stock_transfers"
                " WHERE origin_branch_id=? OR destination_branch_id=?"
                " ORDER BY updated_at DESC, id DESC LIMIT ?",
                (branch_id, branch_id, lim))
        else:
            rows = self._query(
                f"SELECT {cols} FROM stock_transfers"
                " ORDER BY updated_at DESC, id DESC LIMIT ?", (lim,))
        return [{
            "transfer_number": r["transfer_number"],
            "transfer_type": r["transfer_type"],
            "origin_branch_id": zn(r["origin_branch_id"]),
            "destination_branch_id": zn(r["destination_branch_id"]),
            "status": r["status"],
            "updated_at": r["updated_at"],
        } for r in rows]
