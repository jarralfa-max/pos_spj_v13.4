"""DispatchPolicy (master prompt §36). Before dispatching, validate: order
ready, adjustments resolved, driver assigned — package completeness and
ticket generation belong to infrastructure (printing, ORD-28) and are not
re-checked in the domain layer.
"""

from __future__ import annotations

from backend.domain.orders_delivery.enums import CustomerApprovalStatus, FulfillmentStatus
from backend.domain.orders_delivery.exceptions import DispatchNotAllowedError


class DispatchPolicy:
    @staticmethod
    def ensure_can_dispatch(
        *, fulfillment_status: FulfillmentStatus, customer_approval_status: CustomerApprovalStatus,
        has_assigned_driver: bool,
    ) -> None:
        if fulfillment_status != FulfillmentStatus.READY:
            raise DispatchNotAllowedError(
                f"El pedido no está listo para despachar (estado: {fulfillment_status.value})")
        if customer_approval_status == CustomerApprovalStatus.PENDING:
            raise DispatchNotAllowedError(
                "El pedido tiene un ajuste pendiente de aprobación del cliente")
        if not has_assigned_driver:
            raise DispatchNotAllowedError("No se puede despachar sin repartidor asignado")
