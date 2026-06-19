"""DeliveryPrintPolicy — single source of truth for which document prints at
which status transition.

Two operative documents:
  - DRIVER_OPERATIVE: the driver's ticket (address, items, real quantities,
    amount to collect). Printed when the order goes out for delivery.
  - CUSTOMER_RECEIPT: the final receipt (final total, amount collected, balance,
    method, date, driver). Printed when the order is delivered.

Counter (pickup) orders have no dispatch step, so they only print the customer
receipt on delivery.

Backend in English; documents map to legacy status strings used by the state
machine ("en_ruta", "entregado").
"""
from __future__ import annotations

from enum import Enum


class DeliveryDocument(str, Enum):
    DRIVER_OPERATIVE = "driver_operative"
    CUSTOMER_RECEIPT = "customer_receipt"


# Legacy DB status that triggers dispatch printing. "en_ruta" == IN_TRANSIT.
DISPATCH_STATUS = "en_ruta"
DELIVERED_STATUS = "entregado"

# Counter / pickup workflows do not dispatch a driver.
_COUNTER_WORKFLOWS = frozenset({"counter", "pickup", "sucursal", "mostrador"})


class DeliveryPrintPolicy:
    """Decide the documents to print for a given status transition."""

    def documents_for(self, status: str, workflow_type: str = "") -> tuple[DeliveryDocument, ...]:
        target = (status or "").strip().lower()
        workflow = (workflow_type or "").strip().lower()

        if target == DISPATCH_STATUS:
            # No driver ticket for counter/pickup flows.
            if workflow in _COUNTER_WORKFLOWS:
                return ()
            return (DeliveryDocument.DRIVER_OPERATIVE,)

        if target == DELIVERED_STATUS:
            return (DeliveryDocument.CUSTOMER_RECEIPT,)

        return ()
