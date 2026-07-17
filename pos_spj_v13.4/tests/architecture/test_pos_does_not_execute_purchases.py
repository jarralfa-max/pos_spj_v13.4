"""FASE PUR-1 (§87) — the POS detects needs; it never executes purchases.

The POS-side modules must not write purchases, create purchase orders/receipts,
or create supplier payables. They may only emit replenishment-need events
(POS_REPLENISHMENT_REQUEST / PURCHASE_NEED_DETECTED / …).
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

#: POS-side surfaces that must stay purchase-execution-free.
_POS_FILES = [
    "modulos/ventas.py",
    "modulos/caja.py",
]

_FORBIDDEN = re.compile(
    r"INSERT\s+INTO\s+(compras|ordenes_compra|recepciones)"
    r"|ComprasWriteRepository"
    r"|create_purchase_order"
    r"|CreateDirectPurchase"
    r"|CompleteGoodsReceipt"
    r"|receive_purchase"
    r"|registrar_compra\b",
    re.IGNORECASE,
)


def test_pos_modules_do_not_execute_purchases():
    offenders = []
    for rel in _POS_FILES:
        path = REPO / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in _FORBIDDEN.finditer(text):
            offenders.append(f"{rel}: {match.group(0)}")
    assert not offenders, (
        "El POS no debe ejecutar compras (detecta necesidades, no abastece):\n"
        + "\n".join(offenders))


def test_procurement_need_events_are_defined():
    """The canonical replenishment-need vocabulary must exist for the POS to emit."""
    from backend.domain.procurement.events import ReplenishmentNeedEvents

    assert ReplenishmentNeedEvents.STOCK_REPLENISHMENT_REQUIRED
    assert ReplenishmentNeedEvents.PURCHASE_NEED_DETECTED
    assert ReplenishmentNeedEvents.CUSTOMER_ORDER_REQUIRES_PURCHASE
