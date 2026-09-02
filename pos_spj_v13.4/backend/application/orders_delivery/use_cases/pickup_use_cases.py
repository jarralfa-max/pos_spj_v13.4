"""Pickup/counter use cases (master prompt §30: listo → notificación →
validación de identidad → cobro si pendiente → entrega). §30's own
notification step now runs (ORD-23) via `OrdersDeliveryWhatsAppClient`, as a
best-effort side effect AFTER the order-side transaction has already
committed — a WhatsApp delivery failure never un-marks the order ready.
"""

from __future__ import annotations

import logging
import secrets

from backend.application.orders_delivery.dto import CustomerOrderDTO
from backend.application.orders_delivery.permissions import OrdersDeliveryPermissions
from backend.application.orders_delivery.result import OrderResult, fail_from_domain_error
from backend.application.orders_delivery.use_cases._base import _OrdersDeliveryBaseUseCase
from backend.domain.orders_delivery.exceptions import OrderNotFoundError, OrdersDeliveryDomainError
from backend.infrastructure.db.repositories.orders_delivery.unit_of_work import (
    OrdersDeliveryUnitOfWork,
)
from backend.infrastructure.integrations.orders_delivery_whatsapp_client import (
    OrdersDeliveryWhatsAppClient,
)

logger = logging.getLogger("spj.orders_delivery.pickup")


def _generate_verification_code() -> str:
    """A short numeric code, not a UUID — this is read aloud/typed by a
    customer at a counter, not machine-to-machine."""
    return f"{secrets.randbelow(1_000_000):06d}"


class MarkReadyForPickupUseCase(_OrdersDeliveryBaseUseCase):
    def __init__(self, authorization=None, *,
                 whatsapp_client: OrdersDeliveryWhatsAppClient | None = None) -> None:
        super().__init__(authorization)
        self._whatsapp = whatsapp_client or OrdersDeliveryWhatsAppClient()

    def execute(self, connection, *, order_id: str, actor_user_id: str,
                operation_id: str) -> OrderResult:
        try:
            self._auth.require(actor_user_id, OrdersDeliveryPermissions.PREPARATION_COMPLETE)
        except OrdersDeliveryDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        with OrdersDeliveryUnitOfWork(connection) as uow:
            order = uow.orders.get(order_id)
            if order is None:
                return fail_from_domain_error(
                    OrderNotFoundError(f"Pedido {order_id} no existe"), operation_id=operation_id)
            code = _generate_verification_code()
            try:
                order.mark_ready_for_pickup(verification_code=code)
            except OrdersDeliveryDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.orders.save(order)

        notification_sent = False
        try:
            notification_sent = self._whatsapp.notify_ready_for_pickup(
                phone=order.contact_phone or "", order_number=order.order_number or order.id)
        except Exception as exc:  # noqa: BLE001 - never fail "ready" over a notification
            logger.warning("Notificación de pedido listo no enviada para %s: %s", order.id, exc)
        return OrderResult.ok(
            "Pedido listo para recoger", entity_id=order.id, operation_id=operation_id,
            order=CustomerOrderDTO.from_entity(order), verification_code=code,
            notification_sent=notification_sent)


class CompletePickupUseCase(_OrdersDeliveryBaseUseCase):
    def execute(self, connection, *, order_id: str, presented_code: str, actor_user_id: str,
                operation_id: str) -> OrderResult:
        try:
            self._auth.require(actor_user_id, OrdersDeliveryPermissions.DELIVERY_CONFIRM)
        except OrdersDeliveryDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        with OrdersDeliveryUnitOfWork(connection) as uow:
            order = uow.orders.get(order_id)
            if order is None:
                return fail_from_domain_error(
                    OrderNotFoundError(f"Pedido {order_id} no existe"), operation_id=operation_id)
            try:
                order.complete_pickup(presented_code=presented_code)
            except OrdersDeliveryDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.orders.save(order)
        return OrderResult.ok(
            "Pedido entregado en mostrador", entity_id=order.id, operation_id=operation_id,
            order=CustomerOrderDTO.from_entity(order))
