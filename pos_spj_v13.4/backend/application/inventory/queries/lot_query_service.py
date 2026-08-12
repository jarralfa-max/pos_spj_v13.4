"""LotQueryService — the read the Lotes UI consults (§46).

Read-only projection over ``inventory_lots``: lists a product's lots ordered by
expiration (FEFO-friendly), exposing code, origin, quality status and dates. It
never writes — lot creation/quality changes go through the lot use cases.
"""

from __future__ import annotations

from backend.infrastructure.db.repositories.inventory.base import (
    InventoryRepositoryBase,
    zn,
)


class LotQueryService(InventoryRepositoryBase):
    def list_for_product(self, *, product_id: str,
                         branch_id: str | None = None) -> list[dict]:
        """Lots of a product (optionally scoped to a branch), earliest expiry
        first. Rows carry code, origin, quality status and dates for display."""
        pid = str(product_id or "").strip()
        if not pid:
            return []
        if branch_id:
            rows = self._query(
                "SELECT id, lot_code, origin_type, quality_status, expiration_date,"
                " received_at, branch_id FROM inventory_lots"
                " WHERE product_id=? AND branch_id=? ORDER BY expiration_date",
                (pid, branch_id))
        else:
            rows = self._query(
                "SELECT id, lot_code, origin_type, quality_status, expiration_date,"
                " received_at, branch_id FROM inventory_lots"
                " WHERE product_id=? ORDER BY expiration_date", (pid,))
        return [dict(r) | {"expiration_date": zn(r["expiration_date"]),
                           "received_at": zn(r["received_at"])} for r in rows]

    def get_lot(self, *, lot_id: str) -> dict | None:
        """Full raw lot row (§26 detalle) — for the detail view, not the
        display-ready list rows."""
        lid = str(lot_id or "").strip()
        if not lid:
            return None
        return self._query_one("SELECT * FROM inventory_lots WHERE id=?", (lid,))
