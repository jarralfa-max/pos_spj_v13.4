from __future__ import annotations

from typing import Any

from core.delivery.domain.events import DeliveryEvents
from core.delivery.application.ports import InventoryReservationPort


class DeliveryInventoryProjectionService:
    """Routes delivery inventory events to an InventoryReservationPort."""

    def __init__(self, inventory_reservations: InventoryReservationPort) -> None:
        self.inventory_reservations = inventory_reservations

    def handlers(self):
        return {
            DeliveryEvents.ORDER_RESERVED.value: self.handle_order_reserved,
            DeliveryEvents.INVENTORY_RELEASE_REQUIRED.value: self.handle_inventory_release_required,
            DeliveryEvents.INVENTORY_COMMIT_REQUIRED.value: self.handle_inventory_commit_required,
        }

    def handle_order_reserved(self, payload: dict[str, Any]) -> dict[str, int]:
        order_id = int(payload.get("order_id") or 0)
        operation_id = str(payload.get("operation_id") or f"delivery:{order_id}")
        return self.inventory_reservations.reserve_for_order(
            order_id=order_id,
            items=list(payload.get("items") or []),
            branch_id=int(payload.get("branch_id") or payload.get("sucursal_id") or 1),
            operation_id=operation_id,
        )

    def handle_inventory_release_required(self, payload: dict[str, Any]) -> dict[str, int]:
        order_id = int(payload.get("order_id") or 0)
        operation_id = str(payload.get("operation_id") or f"delivery:{order_id}")
        return self.inventory_reservations.release_for_order(
            order_id=order_id,
            operation_id=operation_id,
            reason=str(payload.get("reason") or ""),
        )

    def handle_inventory_commit_required(self, payload: dict[str, Any]) -> dict[str, int]:
        order_id = int(payload.get("order_id") or 0)
        operation_id = str(payload.get("operation_id") or f"delivery:{order_id}")
        return self.inventory_reservations.commit_for_order(
            order_id=order_id,
            items=list(payload.get("items") or []),
            branch_id=int(payload.get("branch_id") or payload.get("sucursal_id") or 1),
            operation_id=operation_id,
        )
