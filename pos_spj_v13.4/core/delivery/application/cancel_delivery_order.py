from __future__ import annotations

from typing import Any

from core.delivery.domain.value_objects import DeliveryStatus

from .change_delivery_status import ChangeDeliveryStatusUseCase


class CancelDeliveryOrderUseCase:
    def __init__(self, change_status_use_case: ChangeDeliveryStatusUseCase) -> None:
        self.change_status_use_case = change_status_use_case

    def execute(self, order_id: int, usuario: str = "sistema", motivo: str = "") -> dict[str, Any]:
        self.change_status_use_case.execute(order_id, DeliveryStatus.CANCELLED.value, usuario=usuario, responsable="", observacion=motivo)
        return {"order_id": order_id, "status": DeliveryStatus.CANCELLED.value, "motivo": motivo}
