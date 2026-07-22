"""Canonical inventory events (§58).

All inventory domain events are published post-commit with the minimum payload
(§58): distinct event_id / operation_id / entity_id, plus product/lot/branch/
warehouse/location/user context. These replace the legacy ad-hoc signals
(STOCK_ACTUALIZADO, INVENTARIO_CAMBIADO, TRASPASO_REALIZADO, RECEPCION_COMPLETADA).
"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.shared.ids import new_uuid


class InventoryEvents:
    # warehouses / locations
    WAREHOUSE_CREATED = "WAREHOUSE_CREATED"
    WAREHOUSE_ACTIVATED = "WAREHOUSE_ACTIVATED"
    WAREHOUSE_BLOCKED = "WAREHOUSE_BLOCKED"
    LOCATION_CREATED = "LOCATION_CREATED"
    LOCATION_BLOCKED = "LOCATION_BLOCKED"

    # ledger / balance
    INVENTORY_MOVEMENT_POSTED = "INVENTORY_MOVEMENT_POSTED"
    INVENTORY_MOVEMENT_REVERSED = "INVENTORY_MOVEMENT_REVERSED"
    INVENTORY_BALANCE_CHANGED = "INVENTORY_BALANCE_CHANGED"

    # reservations
    INVENTORY_RESERVED = "INVENTORY_RESERVED"
    INVENTORY_RESERVATION_RELEASED = "INVENTORY_RESERVATION_RELEASED"
    INVENTORY_ALLOCATED = "INVENTORY_ALLOCATED"

    # transfers
    INVENTORY_TRANSFER_CREATED = "INVENTORY_TRANSFER_CREATED"
    INVENTORY_TRANSFER_APPROVED = "INVENTORY_TRANSFER_APPROVED"
    INVENTORY_TRANSFER_DISPATCHED = "INVENTORY_TRANSFER_DISPATCHED"
    INVENTORY_TRANSFER_RECEIVED = "INVENTORY_TRANSFER_RECEIVED"
    INVENTORY_TRANSFER_DIFFERENCE_DETECTED = "INVENTORY_TRANSFER_DIFFERENCE_DETECTED"

    # counts / adjustments
    INVENTORY_COUNT_STARTED = "INVENTORY_COUNT_STARTED"
    INVENTORY_COUNT_CONFIRMED = "INVENTORY_COUNT_CONFIRMED"
    INVENTORY_COUNT_VARIANCE_DETECTED = "INVENTORY_COUNT_VARIANCE_DETECTED"
    INVENTORY_ADJUSTMENT_POSTED = "INVENTORY_ADJUSTMENT_POSTED"

    # lots
    INVENTORY_LOT_CREATED = "INVENTORY_LOT_CREATED"
    INVENTORY_LOT_BLOCKED = "INVENTORY_LOT_BLOCKED"
    INVENTORY_LOT_RELEASED = "INVENTORY_LOT_RELEASED"
    INVENTORY_LOT_EXPIRING = "INVENTORY_LOT_EXPIRING"
    INVENTORY_LOT_EXPIRED = "INVENTORY_LOT_EXPIRED"

    # quality / quarantine
    INVENTORY_QUARANTINED = "INVENTORY_QUARANTINED"
    INVENTORY_QUARANTINE_RELEASED = "INVENTORY_QUARANTINE_RELEASED"

    # stock health
    INVENTORY_STOCK_LOW = "INVENTORY_STOCK_LOW"
    INVENTORY_STOCK_CRITICAL = "INVENTORY_STOCK_CRITICAL"
    INVENTORY_STOCK_OUT = "INVENTORY_STOCK_OUT"

    # cold chain / negative
    INVENTORY_TEMPERATURE_ALERT = "INVENTORY_TEMPERATURE_ALERT"
    INVENTORY_NEGATIVE_DETECTED = "INVENTORY_NEGATIVE_DETECTED"

    # waste / disposal (→ Finance valuation, §30)
    INVENTORY_WASTE_RECORDED = "INVENTORY_WASTE_RECORDED"

    # traceability / genealogy (§32-33)
    INVENTORY_TRACEABILITY_LINKED = "INVENTORY_TRACEABILITY_LINKED"
    INVENTORY_RECALL_INITIATED = "INVENTORY_RECALL_INITIATED"

    # replenishment / planning (§34)
    INVENTORY_REPLENISHMENT_SUGGESTED = "INVENTORY_REPLENISHMENT_SUGGESTED"
    INVENTORY_REORDER_POINT_REACHED = "INVENTORY_REORDER_POINT_REACHED"

    # notifications
    INVENTORY_NOTIFICATION_CREATED = "INVENTORY_NOTIFICATION_CREATED"
    INVENTORY_WHATSAPP_ALERT_SENT = "INVENTORY_WHATSAPP_ALERT_SENT"


ALL_INVENTORY_EVENTS = frozenset(
    v for k, v in vars(InventoryEvents).items()
    if not k.startswith("_") and isinstance(v, str)
)


def build_event_payload(
    event_name: str,
    *,
    operation_id: str,
    entity_id: str,
    product_id: str | None = None,
    lot_id: str | None = None,
    branch_id: str | None = None,
    warehouse_id: str | None = None,
    location_id: str | None = None,
    user_id: str | None = None,
    device_id: str | None = None,
    source_module: str = "inventory",
    **extra,
) -> dict:
    if event_name not in ALL_INVENTORY_EVENTS:
        raise ValueError(f"Evento de inventario desconocido: {event_name}")
    payload = {
        "event_id": new_uuid(),
        "event_name": event_name,
        "operation_id": operation_id,
        "entity_id": entity_id,
        "product_id": product_id,
        "lot_id": lot_id,
        "branch_id": branch_id,
        "warehouse_id": warehouse_id,
        "location_id": location_id,
        "user_id": user_id,
        "device_id": device_id,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_module": source_module,
    }
    payload.update(extra)
    return payload
