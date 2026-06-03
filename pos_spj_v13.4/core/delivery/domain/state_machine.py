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

ACTION_PREPARE = "preparacion"
ACTION_SEND_TO_ROUTE = "en_ruta"
ACTION_DELIVER = "entregado"
ACTION_CANCEL = "cancelado"
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
        if status == DeliveryStatus.PROGRAMADO and not data.get("activated"):
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
        if current == DeliveryStatus.ENTREGADO:
            raise ValueError("Pedido entregado no puede regresar sin proceso explícito de reverso.")
        if current == DeliveryStatus.CANCELADO:
            if not self.allow_cancelled_reactivation or target != DeliveryStatus.PENDIENTE:
                raise ValueError("Pedido cancelado solo puede reactivarse a pendiente.")
            return
        if workflow == DeliveryWorkflowType.SCHEDULED and target in {
            DeliveryStatus.PREPARACION,
            DeliveryStatus.EN_RUTA,
            DeliveryStatus.ENTREGADO,
        }:
            raise ValueError("Pedido programado: primero debe activarse antes de pasar a flujo operativo.")
        if workflow == DeliveryWorkflowType.COUNTER and target == DeliveryStatus.EN_RUTA:
            raise ValueError("Flujo mostrador no permite estado 'en_ruta'.")
        if workflow == DeliveryWorkflowType.DELIVERY and current == DeliveryStatus.PREPARACION and target == DeliveryStatus.ENTREGADO:
            raise ValueError("Flujo delivery debe pasar por 'en_ruta' antes de entregarse.")
        if target == DeliveryStatus.ENTREGADO and not has_responsible:
            raise ValueError("No se puede entregar sin responsable.")
        if target in {DeliveryStatus.EN_RUTA, DeliveryStatus.ENTREGADO} and has_pending_adjustment:
            raise ValueError("Hay un ajuste de peso/cantidad pendiente de aceptación del cliente.")

        allowed: dict[DeliveryStatus, tuple[DeliveryStatus, ...]] = {
            DeliveryStatus.PENDIENTE: (DeliveryStatus.PREPARACION, DeliveryStatus.CANCELADO),
            DeliveryStatus.PREPARACION: (DeliveryStatus.EN_RUTA, DeliveryStatus.ENTREGADO, DeliveryStatus.CANCELADO),
            DeliveryStatus.EN_RUTA: (DeliveryStatus.ENTREGADO, DeliveryStatus.CANCELADO),
            DeliveryStatus.PROGRAMADO: (DeliveryStatus.PENDIENTE, DeliveryStatus.CANCELADO),
            DeliveryStatus.CANCELADO: (DeliveryStatus.PENDIENTE,),
            DeliveryStatus.ENTREGADO: (),
        }
        if target not in allowed[current]:
            raise ValueError(f"Transición delivery inválida: {current.value} -> {target.value}.")

    def get_valid_actions(self, order: DeliveryOrder | Mapping[str, Any]) -> list[str]:
        data = self._data(order)
        status = normalize_status(data.get("estado"))
        workflow = self.infer_workflow(order)
        has_pending_adjustment = self._has_pending_adjustment(data)

        if status == DeliveryStatus.PROGRAMADO:
            return [ACTION_ACTIVATE_SCHEDULED, ACTION_RESCHEDULE, ACTION_CANCEL]
        if status == DeliveryStatus.PENDIENTE:
            return [ACTION_PREPARE, ACTION_CANCEL]
        if status == DeliveryStatus.PREPARACION:
            actions = [ACTION_ADJUST_WEIGHT, ACTION_CANCEL]
            if workflow == DeliveryWorkflowType.COUNTER:
                actions.insert(1, ACTION_DELIVER)
            else:
                actions[1:1] = [ACTION_ASSIGN_DRIVER, ACTION_SEND_TO_ROUTE]
            if has_pending_adjustment:
                actions = [a for a in actions if a not in {ACTION_SEND_TO_ROUTE, ACTION_DELIVER}]
            return actions
        if status == DeliveryStatus.EN_RUTA:
            actions = [ACTION_DELIVER, ACTION_NOTIFY_WHATSAPP]
            if has_pending_adjustment:
                actions = [a for a in actions if a != ACTION_DELIVER]
            return actions
        if status == DeliveryStatus.ENTREGADO:
            return [ACTION_PRINT]
        if status == DeliveryStatus.CANCELADO:
            return [ACTION_REACTIVATE] if self.allow_cancelled_reactivation else []
        return []
