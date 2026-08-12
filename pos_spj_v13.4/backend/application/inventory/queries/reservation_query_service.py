"""ReservationQueryService — the read the Reservas UI consults (§22).

Read-only projection over ``inventory_reservation``: lists a product's active
reservations (pending/confirmed/allocated/…) for a branch, oldest first. It never
writes — reservations are created/released only by their use cases.
"""

from __future__ import annotations

from backend.infrastructure.db.repositories.inventory.base import (
    InventoryRepositoryBase,
    to_decimal,
    zn,
)

_ACTIVE = ("PENDING", "CONFIRMED", "PARTIALLY_ALLOCATED", "ALLOCATED",
           "PARTIALLY_FULFILLED")


class ReservationQueryService(InventoryRepositoryBase):
    def list_active_for_product(self, *, product_id: str,
                                branch_id: str | None = None) -> list[dict]:
        """Active reservations of a product (source, document, quantity, status),
        oldest first. Empty without a product."""
        pid = str(product_id or "").strip()
        if not pid or not branch_id:
            return []
        placeholders = ",".join("?" for _ in _ACTIVE)
        rows = self._query(
            "SELECT id, source, source_document_id, warehouse_id, quantity, status,"
            " created_at FROM inventory_reservation WHERE product_id=? AND branch_id=?"
            f" AND status IN ({placeholders}) ORDER BY created_at",
            (pid, branch_id, *_ACTIVE))
        return [{
            "id": r["id"], "source": r["source"],
            "source_document_id": zn(r["source_document_id"]),
            "warehouse_id": r["warehouse_id"], "quantity": to_decimal(r["quantity"]),
            "status": r["status"],
        } for r in rows]
