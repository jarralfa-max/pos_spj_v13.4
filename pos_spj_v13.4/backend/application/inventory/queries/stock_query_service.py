"""StockQueryService — the read the Existencias UI consults (§14).

Read-only projection over ``inventory_balances``: lists on-hand stock
(quantity or weight != 0) per product / warehouse / bucket, optionally
scoped to a branch and bounded.

It never writes — balances are maintained only by the projection service.
"""

from __future__ import annotations

from backend.infrastructure.db.repositories.inventory.base import (
    InventoryRepositoryBase,
    to_decimal,
)


class StockQueryService(InventoryRepositoryBase):
    def list_on_hand(
        self,
        *,
        branch_id: str | None = None,
        lot_id: str | None = None,
        limit: int = 500,
    ) -> list[dict]:
        """Return on-hand balances ordered by product and warehouse.

        Rows carry the real balance id, branch, warehouse, location, lot,
        inventory bucket/status, quantity, weight and reserved quantity.

        ``lot_id`` optionally narrows the query to balances for one lot.
        """
        cols = (
            "id, "
            "product_id, "
            "branch_id, "
            "warehouse_id, "
            "location_id, "
            "lot_id, "
            "inventory_status, "
            "quantity, "
            "weight, "
            "reserved_quantity"
        )

        lim = max(1, int(limit))

        where = "(quantity <> '0' OR weight <> '0')"
        params: tuple = ()

        if branch_id:
            where += " AND branch_id=?"
            params += (branch_id,)

        if lot_id:
            where += " AND lot_id=?"
            params += (lot_id,)

        rows = self._query(
            f"SELECT {cols} "
            f"FROM inventory_balances "
            f"WHERE {where} "
            "ORDER BY product_id, warehouse_id, inventory_status "
            "LIMIT ?",
            params + (lim,),
        )

        return [
            {
                "id": row["id"],
                "product_id": row["product_id"],
                "branch_id": row["branch_id"],
                "warehouse_id": row["warehouse_id"],
                "location_id": row["location_id"],
                "lot_id": row["lot_id"],
                "inventory_status": row["inventory_status"],
                "quantity": to_decimal(row["quantity"]),
                "weight": to_decimal(row["weight"]),
                "reserved_quantity": to_decimal(row["reserved_quantity"]),
            }
            for row in rows
        ]