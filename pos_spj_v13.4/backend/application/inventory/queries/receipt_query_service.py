"""ReceiptQueryService — the read the Inventario «Recepciones» UI consults (§15).

Read-only projection over ``inventory_ledger`` filtered to inbound receipt
movements — purchase/direct-purchase receipts, transfer receipts and production
output — that bring stock into inventory. Most recent first, optionally scoped to
a branch and bounded. It never writes; movements are appended only by the posting
use cases.
"""

from __future__ import annotations

from backend.infrastructure.db.repositories.inventory.base import (
    InventoryRepositoryBase,
    zn,
)

#: Movement types that represent goods being received into inventory (§15).
RECEIPT_MOVEMENT_TYPES = (
    "PURCHASE_RECEIPT",
    "DIRECT_PURCHASE_RECEIPT",
    "TRANSFER_RECEIPT",
    "PRODUCTION_OUTPUT",
)


class ReceiptQueryService(InventoryRepositoryBase):
    def list_recent(self, *, branch_id: str | None = None,
                    limit: int = 200) -> list[dict]:
        """Recent inbound receipts (most recent first), optionally scoped to a
        branch and bounded so the UI never pulls the whole ledger."""
        cols = ("id, movement_type, branch_id, warehouse_id, source_module,"
                " source_document_type, source_document_id, status, occurred_at")
        lim = max(1, int(limit))
        marks = ",".join("?" for _ in RECEIPT_MOVEMENT_TYPES)
        where = f"movement_type IN ({marks})"
        params: tuple = tuple(RECEIPT_MOVEMENT_TYPES)
        if branch_id:
            where += " AND branch_id=?"
            params += (branch_id,)
        rows = self._query(
            f"SELECT {cols} FROM inventory_ledger WHERE {where}"
            " ORDER BY occurred_at DESC, id DESC LIMIT ?", params + (lim,))
        return [dict(r) | {"source_document_id": zn(r["source_document_id"])}
                for r in rows]

    def status_for_document(self, source_document_id: str) -> dict | None:
        """Posting status of the most recent inbound receipt movement for a
        single source document (e.g. a goods receipt/purchase order id).
        Narrow, indexed single-lookup counterpart to ``list_recent`` — used by
        other bounded contexts (via a port/adapter) that only need to know
        whether *their* document has posted into inventory yet, never the
        whole recent ledger window."""
        cols = ("id, movement_type, branch_id, warehouse_id, source_module,"
                " source_document_type, source_document_id, status, occurred_at")
        marks = ",".join("?" for _ in RECEIPT_MOVEMENT_TYPES)
        rows = self._query(
            f"SELECT {cols} FROM inventory_ledger"
            f" WHERE movement_type IN ({marks}) AND source_document_id=?"
            " ORDER BY occurred_at DESC, id DESC LIMIT 1",
            tuple(RECEIPT_MOVEMENT_TYPES) + (source_document_id,))
        if not rows:
            return None
        row = rows[0]
        return dict(row) | {"source_document_id": zn(row["source_document_id"])}
