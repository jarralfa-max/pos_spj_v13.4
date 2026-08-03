"""WeightQueryService — the read the Inventario «Peso variable» UI consults (§18).

Read-only projection over ``inventory_balances``: lists catch-weight stock
(``weight`` ≠ 0) per product / warehouse / bucket, optionally scoped to a branch
and bounded. Surfaces both the piece count and the captured weight so a sucursal
sees how much variable-weight product it holds. It never writes — balances are
maintained only by the projection service.
"""

from __future__ import annotations

from backend.infrastructure.db.repositories.inventory.base import (
    InventoryRepositoryBase,
    to_decimal,
)


class WeightQueryService(InventoryRepositoryBase):
    def list_catch_weight(self, *, branch_id: str | None = None,
                          limit: int = 500) -> list[dict]:
        """Catch-weight balances (``weight`` ≠ 0), ordered by product then
        warehouse. Rows carry product, warehouse, bucket, quantity (pieces),
        weight and reserved weight."""
        cols = ("product_id, warehouse_id, inventory_status, quantity, weight,"
                " reserved_weight")
        lim = max(1, int(limit))
        where = "weight <> '0'"
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
            "weight": to_decimal(r["weight"]),
            "reserved_weight": to_decimal(r["reserved_weight"]),
        } for r in rows]
