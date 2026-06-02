from __future__ import annotations

from typing import Any

from core.delivery.projections.sale_delivery_projection import SaleDeliveryProjectionService

from .ports import EventPublisher, NoopPublisher


class ActivateScheduledOrderUseCase:
    def __init__(
        self,
        *,
        db,
        repository,
        sale_projection: SaleDeliveryProjectionService | None = None,
        publisher: EventPublisher = NoopPublisher,
    ) -> None:
        self.db = db
        self.repository = repository
        self.sale_projection = sale_projection
        self.publisher = publisher

    def execute(self, order_id: int, usuario: str = "sistema") -> dict[str, Any]:
        order = self.repository.get_order(order_id) or {}
        if not order:
            raise ValueError("Pedido no encontrado.")

        current_status = (order.get("estado") or "").strip().lower()
        if current_status not in ("programado", "scheduled"):
            raise ValueError("Solo se pueden activar pedidos en estado programado.")

        delivery_type = (order.get("delivery_type") or order.get("tipo_entrega") or "").strip().lower()
        target_workflow = "counter" if delivery_type in ("pickup", "sucursal") else "delivery"

        self.repository.activate_scheduled_order(order_id, target_workflow, usuario=usuario)
        if self.sale_projection is not None:
            self.sale_projection.project_scheduled_activation(order.get("venta_id"), target_workflow)

        self.publisher("WHATSAPP_SCHEDULED_ORDER_ACTIVATED", {
            "order_id": order_id,
            "workflow_type": target_workflow,
            "usuario": usuario,
            "sucursal_id": int(order.get("sucursal_id") or 1),
        })
        return {"order_id": order_id, "workflow_type": target_workflow, "status": "pending"}
