"""CustomerOrder lifecycle invariants (master prompt §14-17, §42). Mirrors
backend/domain/sales/policies/lifecycle_policies.py's `SaleLifecyclePolicy`
shape exactly — an enum-based transition table so application services can
validate rows from repositories without reconstructing a full aggregate,
while `CustomerOrder` itself reuses the same table (§16: "OrderStateMachine
... la UI y la PWA deben consultar acciones válidas, no duplicar reglas").
"""

from __future__ import annotations

from backend.domain.orders_delivery.enums import FulfillmentType, OrderStatus
from backend.domain.orders_delivery.exceptions import (
    DeliveryAddressRequiredError,
    InvalidOrderStateError,
    OrderCancellationNotAllowedError,
    OrderConfirmationRequiredError,
    OrderEmptyError,
)


class OrderLifecyclePolicy:
    ACTIVE_STATUSES = frozenset({
        OrderStatus.DRAFT, OrderStatus.PENDING_CONFIRMATION,
        OrderStatus.CONFIRMED, OrderStatus.IN_FULFILLMENT,
    })
    FINAL_STATUSES = frozenset({
        OrderStatus.CANCELLED, OrderStatus.CLOSED, OrderStatus.REVERSED,
    })
    LINE_MUTABLE_STATUSES = frozenset({OrderStatus.DRAFT, OrderStatus.PENDING_CONFIRMATION})

    TRANSITIONS = {
        (OrderStatus.DRAFT, OrderStatus.PENDING_CONFIRMATION),
        (OrderStatus.DRAFT, OrderStatus.CONFIRMED),
        (OrderStatus.PENDING_CONFIRMATION, OrderStatus.CONFIRMED),
        (OrderStatus.PENDING_CONFIRMATION, OrderStatus.CANCELLED),
        (OrderStatus.CONFIRMED, OrderStatus.IN_FULFILLMENT),
        (OrderStatus.CONFIRMED, OrderStatus.CANCELLED),
        (OrderStatus.IN_FULFILLMENT, OrderStatus.COMPLETED),
        (OrderStatus.IN_FULFILLMENT, OrderStatus.CANCELLED),
        (OrderStatus.DRAFT, OrderStatus.CANCELLED),
        (OrderStatus.COMPLETED, OrderStatus.CLOSED),
        (OrderStatus.COMPLETED, OrderStatus.REVERSED),
    }

    @classmethod
    def normalize(cls, status: OrderStatus | str) -> OrderStatus:
        if isinstance(status, OrderStatus):
            return status
        try:
            return OrderStatus(str(status))
        except ValueError as exc:
            raise InvalidOrderStateError(f"Unknown order status: {status}") from exc

    @classmethod
    def is_line_mutable(cls, status: OrderStatus | str) -> bool:
        return cls.normalize(status) in cls.LINE_MUTABLE_STATUSES

    @classmethod
    def ensure_transition(cls, *, current: OrderStatus | str, target: OrderStatus | str) -> None:
        current_status, target_status = cls.normalize(current), cls.normalize(target)
        if current_status in cls.FINAL_STATUSES:
            raise InvalidOrderStateError("Final orders cannot transition")
        if (current_status, target_status) not in cls.TRANSITIONS:
            raise InvalidOrderStateError(
                f"Invalid order transition: {current_status.value} -> {target_status.value}")


class OrderConfirmationPolicy:
    """Master prompt §17: a draft order cannot be confirmed without at least
    one line and a positive total — mirrors `CheckoutPolicy` in Sales."""

    #: Modalidades que llevan el pedido a un domicilio: sin dirección no hay a dónde
    #: entregar ni zona que fije el costo de envío. `SetOrderDeliveryAddressUseCase`
    #: resuelve la zona para estas mismas.
    ADDRESS_REQUIRED_FULFILLMENT_TYPES = frozenset({
        FulfillmentType.HOME_DELIVERY, FulfillmentType.BRANCH_DELIVERY,
        FulfillmentType.WHOLESALE_DELIVERY, FulfillmentType.SCHEDULED_DELIVERY,
        FulfillmentType.EXPRESS_DELIVERY, FulfillmentType.ROUTE_DELIVERY,
    })

    @staticmethod
    def ensure_can_confirm(*, status: OrderStatus, line_count: int, total,
                           fulfillment_type: FulfillmentType,
                           has_delivery_address: bool) -> None:
        OrderLifecyclePolicy.ensure_transition(current=status, target=OrderStatus.CONFIRMED)
        if line_count <= 0:
            raise OrderEmptyError("No se puede confirmar un pedido sin artículos")
        if total <= 0:
            raise OrderEmptyError("El total del pedido debe ser mayor a cero")
        if (fulfillment_type in OrderConfirmationPolicy.ADDRESS_REQUIRED_FULFILLMENT_TYPES
                and not has_delivery_address):
            raise DeliveryAddressRequiredError(
                "Un pedido con entrega requiere dirección antes de confirmarse")


class OrderCancellationPolicy:
    """Master prompt §42: cancellation only applies before dispatch. An
    order that has already been delivered must be reversed (§43
    `ReverseDeliveredOrder`, ORD-19+), never cancelled."""

    @staticmethod
    def ensure_can_cancel(*, status: OrderStatus, reason: str) -> None:
        if not (reason or "").strip():
            raise OrderCancellationNotAllowedError("La cancelación requiere un motivo")
        try:
            OrderLifecyclePolicy.ensure_transition(current=status, target=OrderStatus.CANCELLED)
        except InvalidOrderStateError as exc:
            raise OrderCancellationNotAllowedError(str(exc)) from exc


class OrderReservationRequiredPolicy:
    """Master prompt §23: reservation/preparation can only start once the
    order is CONFIRMED — a DRAFT/PENDING_CONFIRMATION order has no
    commitment yet for Inventory to act on."""

    @staticmethod
    def ensure_confirmed(status: OrderStatus) -> None:
        if OrderLifecyclePolicy.normalize(status) not in (
            OrderStatus.CONFIRMED, OrderStatus.IN_FULFILLMENT,
        ):
            raise OrderConfirmationRequiredError(
                "El pedido debe estar confirmado antes de reservar/preparar")
