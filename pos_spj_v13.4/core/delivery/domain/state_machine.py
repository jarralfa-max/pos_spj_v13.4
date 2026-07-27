from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Mapping

from .entities import DeliveryOrder
from .states import (
    AdjustmentStatus,
    DeliveryStatus,
    DeliveryType,
    DeliveryWorkflowType,
    normalize_adjustment_status,
    normalize_delivery_type,
    normalize_status,
    normalize_workflow_type,
)

ACTION_PREPARE = "preparing"
ACTION_SEND_TO_ROUTE = "in_transit"
ACTION_DELIVER = "delivered"
ACTION_CANCEL = "cancelled"
ACTION_REACTIVATE = "reactivar"
ACTION_ACTIVATE_SCHEDULED = "activar_programado"
ACTION_RESCHEDULE = "reprogramar"
ACTION_ADJUST_WEIGHT = "ajustar_peso"
ACTION_ASSIGN_DRIVER = "asignar"
ACTION_NOTIFY_WHATSAPP = "notificar_wa"
ACTION_PRINT = "imprimir"


class DeliveryStateMachine:
    """Pure delivery workflow rules.

    This class intentionally returns domain action keys only. UI labels/icons must
    be mapped outside the domain layer.
    """

    def __init__(self, *, allow_cancelled_reactivation: bool = True) -> None:
        self.allow_cancelled_reactivation = allow_cancelled_reactivation

    @staticmethod
    def _data(order: DeliveryOrder | Mapping[str, Any]) -> dict[str, Any]:
        if isinstance(order, DeliveryOrder):
            return asdict(order)
        if isinstance(order, Mapping):
            return dict(order)
        if is_dataclass(order):
            return asdict(order)
        return dict(getattr(order, "__dict__", {}))

    def normalize_status(self, status: Any) -> DeliveryStatus:
        return normalize_status(status)

    @staticmethod
    def _has_pending_adjustment(data: Mapping[str, Any]) -> bool:
        if data.get("adjustment_pending") or data.get("has_pending_adjustment"):
            return True
        for item in data.get("items") or ():
            item_data = item if isinstance(item, Mapping) else getattr(item, "__dict__", {})
            try:
                if normalize_adjustment_status(item_data.get("adjustment_status")) == AdjustmentStatus.PENDING_CUSTOMER:
                    return True
            except ValueError:
                continue
        return False

    def infer_workflow(self, order: DeliveryOrder | Mapping[str, Any]) -> DeliveryWorkflowType:
        data = self._data(order)
        explicit_workflow = normalize_workflow_type(data.get("workflow_type"))
        if explicit_workflow:
            return explicit_workflow

        status = normalize_status(data.get("estado"))
        if status == DeliveryStatus.SCHEDULED and not data.get("activated"):
            return DeliveryWorkflowType.SCHEDULED

        delivery_type = normalize_delivery_type(data.get("delivery_type") or data.get("tipo_entrega"))
        if delivery_type in {DeliveryType.PICKUP, DeliveryType.SUCURSAL}:
            return DeliveryWorkflowType.COUNTER
        return DeliveryWorkflowType.DELIVERY

    def assert_can_transition(self, order: DeliveryOrder | Mapping[str, Any], target_status: Any) -> None:
        data = self._data(order)
        current = normalize_status(data.get("estado"))
        target = normalize_status(target_status)
        workflow = self.infer_workflow(order)
        has_pending_adjustment = self._has_pending_adjustment(data)
        has_responsible = bool(
            data.get("responsable_entrega")
            or data.get("responsable")
            or data.get("driver_id")
            or data.get("has_responsible_party")
        )

        if current == target:
            return
        if current == DeliveryStatus.DELIVERED:
            raise ValueError("Pedido entregado no puede regresar sin proceso explícito de reverso.")
        if current == DeliveryStatus.CANCELLED:
            if not self.allow_cancelled_reactivation or target != DeliveryStatus.PENDING:
                raise ValueError("Pedido cancelado solo puede reactivarse a pendiente.")
            return
        if workflow == DeliveryWorkflowType.SCHEDULED and target in {
            DeliveryStatus.PREPARING,
            DeliveryStatus.IN_TRANSIT,
            DeliveryStatus.DELIVERED,
        }:
            raise ValueError("Pedido programado: primero debe activarse antes de pasar a flujo operativo.")
        if workflow == DeliveryWorkflowType.COUNTER and target == DeliveryStatus.IN_TRANSIT:
            raise ValueError("Flujo mostrador no permite estado 'in_transit'.")
        if workflow == DeliveryWorkflowType.DELIVERY and current == DeliveryStatus.PREPARING and target == DeliveryStatus.DELIVERED:
            raise ValueError("Flujo delivery debe pasar por 'in_transit' antes de entregarse.")
        if target == DeliveryStatus.DELIVERED and not has_responsible:
            raise ValueError("No se puede entregar sin responsable.")
        if target in {DeliveryStatus.IN_TRANSIT, DeliveryStatus.DELIVERED} and has_pending_adjustment:
            raise ValueError("Hay un ajuste de peso/cantidad pendiente de aceptación del cliente.")

        allowed: dict[DeliveryStatus, tuple[DeliveryStatus, ...]] = {
            DeliveryStatus.PENDING: (DeliveryStatus.PREPARING, DeliveryStatus.CANCELLED),
            DeliveryStatus.PREPARING: (DeliveryStatus.IN_TRANSIT, DeliveryStatus.DELIVERED, DeliveryStatus.CANCELLED),
            DeliveryStatus.IN_TRANSIT: (DeliveryStatus.DELIVERED, DeliveryStatus.CANCELLED),
            DeliveryStatus.SCHEDULED: (DeliveryStatus.PENDING, DeliveryStatus.CANCELLED),
            DeliveryStatus.CANCELLED: (DeliveryStatus.PENDING,),
            DeliveryStatus.DELIVERED: (),
        }
        if target not in allowed[current]:
            raise ValueError(f"Transición delivery inválida: {current.value} -> {target.value}.")

    def get_valid_actions(self, order: DeliveryOrder | Mapping[str, Any]) -> list[str]:
        data = self._data(order)
        status = normalize_status(data.get("estado"))
        workflow = self.infer_workflow(order)
        has_pending_adjustment = self._has_pending_adjustment(data)

        if status == DeliveryStatus.SCHEDULED:
            return [ACTION_ACTIVATE_SCHEDULED, ACTION_RESCHEDULE, ACTION_CANCEL]
        if status == DeliveryStatus.PENDING:
            return [ACTION_PREPARE, ACTION_CANCEL]
        if status == DeliveryStatus.PREPARING:
            actions = [ACTION_ADJUST_WEIGHT, ACTION_CANCEL]
            if workflow == DeliveryWorkflowType.COUNTER:
                actions.insert(1, ACTION_DELIVER)
            else:
                actions[1:1] = [ACTION_ASSIGN_DRIVER, ACTION_SEND_TO_ROUTE]
            if has_pending_adjustment:
                actions = [a for a in actions if a not in {ACTION_SEND_TO_ROUTE, ACTION_DELIVER}]
            return actions
        if status == DeliveryStatus.IN_TRANSIT:
            actions = [ACTION_DELIVER, ACTION_NOTIFY_WHATSAPP]
            if has_pending_adjustment:
                actions = [a for a in actions if a != ACTION_DELIVER]
            return actions
        if status == DeliveryStatus.DELIVERED:
            return [ACTION_PRINT]
        if status == DeliveryStatus.CANCELLED:
            return [ACTION_REACTIVATE] if self.allow_cancelled_reactivation else []
        return []
