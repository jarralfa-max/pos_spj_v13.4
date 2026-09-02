"""PickupPolicy (master prompt §30). Governs the counter/pickup hand-over:
identity validation (a presented code must match) and payment (must be PAID
before hand-over — Pedidos never processes the payment itself, §47, it only
gates on the `PaymentStatus` it already owns as a field).
"""

from __future__ import annotations

from backend.domain.orders_delivery.enums import FulfillmentStatus, FulfillmentType, PaymentStatus
from backend.domain.orders_delivery.exceptions import (
    OrderPreparationNotAllowedError,
    PaymentRequiredForPickupError,
    PickupVerificationFailedError,
)

_PICKUP_FULFILLMENT_TYPES = frozenset({FulfillmentType.COUNTER, FulfillmentType.PICKUP})


class PickupPolicy:
    @staticmethod
    def ensure_is_pickup_order(fulfillment_type: FulfillmentType) -> None:
        if fulfillment_type not in _PICKUP_FULFILLMENT_TYPES:
            raise OrderPreparationNotAllowedError(
                f"{fulfillment_type.value} no es una modalidad de mostrador/recolección")

    @staticmethod
    def ensure_ready(fulfillment_status: FulfillmentStatus) -> None:
        if fulfillment_status != FulfillmentStatus.READY:
            raise OrderPreparationNotAllowedError(
                f"El pedido no está listo para recoger (estado: {fulfillment_status.value})")

    @staticmethod
    def ensure_verification_matches(*, expected_code: str | None, presented_code: str) -> None:
        if not expected_code or expected_code != presented_code:
            raise PickupVerificationFailedError("El código presentado no coincide")

    @staticmethod
    def ensure_paid(payment_status: PaymentStatus) -> None:
        if payment_status != PaymentStatus.PAID:
            raise PaymentRequiredForPickupError(
                f"El pedido debe estar pagado antes de la entrega (estado: {payment_status.value})")
