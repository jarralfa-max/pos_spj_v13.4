"""CanonicalPurchaseStockEntryHandler — the procurement flip (INV-27).

Replaces the legacy PurchaseStockEntryHandler / PurchaseLotEntryHandler on the
live ``PURCHASE_STOCK_ENTRY_REGISTERED`` event. The legacy handlers wrote
``movimientos_inventario`` (trigger → ``inventario_actual``), ``costo_promedio``
and ``productos.existencia`` — i.e. legacy tables. After the corte every stock
writer posts to the canonical ledger, so procurement receipts must too, otherwise
purchased stock never reaches the projection the POS reads.

This maps the live payload onto the born-clean ``PurchaseReceiptHandler``
(PURCHASE_RECEIPT to the ledger, lots by lot_code, unit_cost on the line): it
fills ``branch_id`` from ``warehouse_id`` and defaults each line's location to the
branch (the POS-sellable convention used by the backfill and the other flips).
Idempotent by event_id.
"""

from __future__ import annotations

from backend.application.event_handlers.inventory.purchase_receipt_handler import (
    PurchaseReceiptHandler,
)


class CanonicalPurchaseStockEntryHandler(PurchaseReceiptHandler):
    event_name = "PURCHASE_STOCK_ENTRY_REGISTERED"

    def handle(self, payload: dict) -> None:
        branch = str(payload.get("branch_id") or payload.get("warehouse_id") or "").strip()
        mapped = dict(payload)
        mapped["branch_id"] = branch
        mapped.setdefault("warehouse_id", branch)
        lines = []
        for ln in payload.get("lines") or []:
            line = dict(ln)
            line.setdefault("to_location_id", branch)
            lines.append(line)
        mapped["lines"] = lines
        super().handle(mapped)
