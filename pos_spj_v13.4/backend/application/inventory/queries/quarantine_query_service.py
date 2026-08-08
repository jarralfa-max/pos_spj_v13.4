"""QuarantineQueryService — the read the Cuarentena UI consults (§31).

Read-only projection over ``inventory_quarantine``: lists open quarantines
(OPEN / UNDER_REVIEW / PARTIALLY_RELEASED), optionally scoped to a branch, oldest
first. It never writes — quarantines are opened/released only by their use cases.
"""

from __future__ import annotations

from backend.infrastructure.db.repositories.inventory.base import (
    InventoryRepositoryBase,
    to_decimal,
    zn,
)

_OPEN_STATES = ("OPEN", "UNDER_REVIEW", "PARTIALLY_RELEASED")


class QuarantineQueryService(InventoryRepositoryBase):
    def list_open(self, *, branch_id: str | None = None) -> list[dict]:
        """Open quarantines (oldest first). Rows carry product, lot (id + the
        real code, never just the UUID), reason, quantity and status."""
        placeholders = ",".join("?" for _ in _OPEN_STATES)
        sql = ("SELECT q.id, q.product_id, q.lot_id, l.lot_code, q.reason,"
               " q.quantity, q.status, q.created_at"
               " FROM inventory_quarantine q"
               " LEFT JOIN inventory_lots l ON l.id = q.lot_id"
               f" WHERE q.status IN ({placeholders})")
        params: tuple = tuple(_OPEN_STATES)
        if branch_id:
            sql += " AND q.branch_id=?"
            params += (branch_id,)
        sql += " ORDER BY q.created_at"
        return [{
            "id": r["id"], "product_id": r["product_id"], "lot_id": zn(r["lot_id"]),
            "lot_code": zn(r["lot_code"]),
            "reason": r["reason"], "quantity": to_decimal(r["quantity"]),
            "status": r["status"], "created_at": zn(r["created_at"]),
        } for r in self._query(sql, params)]
