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

Traceability lots (P2): the live event carries ``inventory_unit``/``expiration``/
``lot`` per line (not ``lot_code``), so it derives a ``lot_code`` for lot-tracked
lines — weight-tracked (KG) or carrying an expiration/lot marker — mirroring the
legacy PurchaseLotEntryHandler rule. The code is the explicit ``lot`` when present,
else a deterministic ``{document}-P{product_id}`` so replays never duplicate the
lot. This makes canonical ``inventory_lots`` the sole owner of purchase lots
(meat/poultry/perishables), replacing the legacy ``lotes``/``movimientos_lote``
writes. Idempotent by event_id.
"""

from __future__ import annotations

from backend.application.event_handlers.inventory.purchase_receipt_handler import (
    PurchaseReceiptHandler,
)

_WEIGHT_UNITS = {"KG", "KILO", "KILOS", "KG."}


def _is_lot_tracked(line: dict) -> bool:
    """Legacy rule (PurchaseLotEntryHandler): a line needs a traceability lot when
    it is weight-tracked (KG) or carries an expiration/lot marker."""
    unit = str(line.get("inventory_unit") or "").strip().upper()
    if unit in _WEIGHT_UNITS:
        return True
    return bool(line.get("expiration") or line.get("lot"))


class CanonicalPurchaseStockEntryHandler(PurchaseReceiptHandler):
    event_name = "PURCHASE_STOCK_ENTRY_REGISTERED"

    def handle(self, payload: dict) -> None:
        branch = str(payload.get("branch_id") or payload.get("warehouse_id") or "").strip()
        document = str(payload.get("document_number")
                       or payload.get("goods_receipt_id")
                       or payload.get("document_id")
                       or str(payload.get("event_id") or "")[:8])
        mapped = dict(payload)
        mapped["branch_id"] = branch
        mapped.setdefault("warehouse_id", branch)
        lines = []
        for ln in payload.get("lines") or []:
            line = dict(ln)
            line.setdefault("to_location_id", branch)
            # Derive lot_code for lot-tracked lines so the inherited _ensure_lot
            # creates a canonical inventory_lots lot (legacy parity).
            if (not line.get("lot_code") and not line.get("lot_id")
                    and _is_lot_tracked(line)):
                product_id = str(line.get("product_id") or "")
                explicit = str(line.get("lot") or "").strip()
                line["lot_code"] = explicit or f"{document}-P{product_id}"
            lines.append(line)
        mapped["lines"] = lines
        super().handle(mapped)
