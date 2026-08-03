"""StockQueryService — the read the Existencias UI consults (§14).

Read-only projection over ``inventory_balances``: lists on-hand stock (quantity
or weight ≠ 0) per product / warehouse / bucket, optionally scoped to a branch and
bounded. It never writes — balances are maintained only by the projection service.
"""

from __future__ import annotations

from backend.infrastructure.db.repositories.inventory.base import (
    InventoryRepositoryBase,
    to_decimal,
)


class StockQueryService(InventoryRepositoryBase):
    def list_on_hand(self, *, branch_id: str | None = None,
                     limit: int = 500) -> list[dict]:
        """On-hand balances (quantity or weight ≠ 0), ordered by product then
        warehouse. Rows carry product, warehouse, bucket status and quantity."""
        cols = ("product_id, warehouse_id, inventory_status, quantity, weight,"
                " reserved_quantity")
        lim = max(1, int(limit))
        where = "(quantity <> '0' OR weight <> '0')"
        params: tuple = ()
        if branch_id:
            where += " AND branch_id=?"
            params += (branch_id,)
        rows = self._query(
            f"SELECT {cols} FROM inventory_balances WHERE {where}"
            " ORDER BY product_id, warehouse_id, inventory_status LIMIT ?",
            params + (lim,))
        return [{
            "product_id": r["product_id"], "warehouse_id": r["warehouse_id"],
            "inventory_status": r["inventory_status"],
            "quantity": to_decimal(r["quantity"]),
            "reserved_quantity": to_decimal(r["reserved_quantity"]),
        } for r in rows]
