"""Substitution use cases (master prompt §28-29). Reuses the SAME customer
approval machinery ORD-10/ORD-11 already built for catch-weight
(`CustomerApprovalStatus`, idempotent accept/reject, expiration) — a line
can only have one thing pending customer approval at a time in this domain,
and both concerns share that single gate.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from backend.application.orders_delivery.dto import CustomerOrderDTO
from backend.application.orders_delivery.permissions import OrdersDeliveryPermissions
from backend.application.orders_delivery.result import OrderResult, fail_from_domain_error
from backend.application.orders_delivery.use_cases._base import _OrdersDeliveryBaseUseCase
from backend.domain.orders_delivery.enums import SubstitutionType
from backend.domain.orders_delivery.events import OrderEvents
from backend.domain.orders_delivery.exceptions import OrderNotFoundError, OrdersDeliveryDomainError
from backend.infrastructure.db.repositories.orders_delivery.unit_of_work import (
    OrdersDeliveryUnitOfWork,
)
from backend.infrastructure.integrations.orders_delivery_whatsapp_client import (
    OrdersDeliveryWhatsAppClient,
)

logger = logging.getLogger("spj.orders_delivery.substitution")


class ProposeSubstitutionUseCase(_OrdersDeliveryBaseUseCase):
    def __init__(self, authorization=None, *,
                 whatsapp_client: OrdersDeliveryWhatsAppClient | None = None) -> None:
        super().__init__(authorization)
        self._whatsapp = whatsapp_client or OrdersDeliveryWhatsAppClient()

    def execute(
        self, connection, *, order_id: str, line_id: str, substitute_product_id: str,
        substitution_type: SubstitutionType | str, new_unit_price: Decimal, reason: str,
        actor_user_id: str, operation_id: str, approval_expires_at: str | None = None,
    ) -> OrderResult:
        try:
            self._auth.require(actor_user_id, OrdersDeliveryPermissions.SUBSTITUTION_PROPOSE)
        except OrdersDeliveryDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        substitution_type = (substitution_type if isinstance(substitution_type, SubstitutionType)
                              else SubstitutionType(substitution_type))
        with OrdersDeliveryUnitOfWork(connection) as uow:
            order = uow.orders.get(order_id)
            if order is None:
                return fail_from_domain_error(
                    OrderNotFoundError(f"Pedido {order_id} no existe"), operation_id=operation_id)
            try:
                order.propose_substitution(
                    line_id=line_id, substitute_product_id=substitute_product_id,
                    substitution_type=substitution_type, new_unit_price=new_unit_price,
                    reason=reason, approval_expires_at=approval_expires_at)
            except OrdersDeliveryDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.orders.save(order)
            self._emit(
                uow, OrderEvents.SUBSTITUTION_PROPOSED, aggregate_type="CustomerOrder",
                entity_id=order.id, operation_id=operation_id, branch_id=order.branch_id,
                actor_user_id=actor_user_id, line_id=line_id,
                substitute_product_id=substitute_product_id)

        notification_sent = False
        try:
            notification_sent = self._whatsapp.notify_customer_approval_required(
                phone=order.contact_phone or "", order_number=order.order_number or order.id,
                reason=f"sustitución de producto ({reason})")
        except Exception as exc:  # noqa: BLE001 - never fail the proposal over a notification
            logger.warning("Notificación de aprobación no enviada para pedido %s: %s", order.id, exc)
        return OrderResult.ok(
            "Sustitución propuesta", entity_id=order.id, operation_id=operation_id,
            order=CustomerOrderDTO.from_entity(order), notification_sent=notification_sent)


class AcceptSubstitutionUseCase(_OrdersDeliveryBaseUseCase):
    def execute(self, connection, *, order_id: str, line_id: str, actor_user_id: str,
                operation_id: str) -> OrderResult:
        try:
            self._auth.require(actor_user_id, OrdersDeliveryPermissions.CUSTOMER_APPROVAL_OVERRIDE)
        except OrdersDeliveryDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        with OrdersDeliveryUnitOfWork(connection) as uow:
            order = uow.orders.get(order_id)
            if order is None:
                return fail_from_domain_error(
                    OrderNotFoundError(f"Pedido {order_id} no existe"), operation_id=operation_id)
            try:
                order.accept_substitution(line_id)
            except OrdersDeliveryDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.orders.save(order)
            self._emit(
                uow, OrderEvents.SUBSTITUTION_ACCEPTED, aggregate_type="CustomerOrder",
                entity_id=order.id, operation_id=operation_id, branch_id=order.branch_id,
                actor_user_id=actor_user_id, line_id=line_id)
        return OrderResult.ok(
            "Sustitución aceptada por el cliente", entity_id=order.id, operation_id=operation_id,
            order=CustomerOrderDTO.from_entity(order))


class RejectSubstitutionUseCase(_OrdersDeliveryBaseUseCase):
    def execute(self, connection, *, order_id: str, line_id: str, actor_user_id: str,
                operation_id: str) -> OrderResult:
        try:
            self._auth.require(actor_user_id, OrdersDeliveryPermissions.CUSTOMER_APPROVAL_OVERRIDE)
        except OrdersDeliveryDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        with OrdersDeliveryUnitOfWork(connection) as uow:
            order = uow.orders.get(order_id)
            if order is None:
                return fail_from_domain_error(
                    OrderNotFoundError(f"Pedido {order_id} no existe"), operation_id=operation_id)
            try:
                order.reject_substitution(line_id)
            except OrdersDeliveryDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.orders.save(order)
            self._emit(
                uow, OrderEvents.SUBSTITUTION_REJECTED, aggregate_type="CustomerOrder",
                entity_id=order.id, operation_id=operation_id, branch_id=order.branch_id,
                actor_user_id=actor_user_id, line_id=line_id)
        return OrderResult.ok(
            "Sustitución rechazada por el cliente", entity_id=order.id, operation_id=operation_id,
            order=CustomerOrderDTO.from_entity(order))
