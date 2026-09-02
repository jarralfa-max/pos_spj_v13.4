"""Catch-weight adjustment use cases (master prompt §26-27). `tolerance_pct`
is always supplied by the caller (a configuration value from a future
Configuración section, master prompt §72's `weight_adjustment_tolerance_pct`
— not hardcoded here).

`OverrideWeightAdjustmentUseCase` is the FIRST real caller of
`OrdersDeliveryAuthorizationPolicy.authorize_exception()` (ORD-1 built it,
nothing used it until now) — master prompt §65 names "peso fuera de
tolerancia" explicitly as a hot-authorization case: a supervisor, distinct
from whoever requested the override, force-finalizes an out-of-tolerance
line without waiting for the customer.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal

from backend.application.orders_delivery.dto import CustomerOrderDTO
from backend.application.orders_delivery.permissions import OrdersDeliveryPermissions
from backend.application.orders_delivery.result import OrderResult, fail_from_domain_error
from backend.application.orders_delivery.use_cases._base import _OrdersDeliveryBaseUseCase
from backend.domain.orders_delivery.events import OrderEvents
from backend.domain.orders_delivery.exceptions import (
    OrderLineNotFoundError,
    OrderNotFoundError,
    OrdersDeliveryDomainError,
)
from backend.domain.orders_delivery.policies.catch_weight_adjustment_policy import (
    CatchWeightAdjustmentPolicy,
)
from backend.infrastructure.db.repositories.orders_delivery.unit_of_work import (
    OrdersDeliveryUnitOfWork,
)
from backend.infrastructure.integrations.orders_delivery_whatsapp_client import (
    OrdersDeliveryWhatsAppClient,
)

logger = logging.getLogger("spj.orders_delivery.catch_weight")


def _line_requested_amount(line) -> Decimal:
    if line.catch_weight_enabled and line.requested_weight is not None:
        return line.requested_weight.value
    return line.requested_quantity.value if line.requested_quantity else Decimal("0")


def _line_prepared_amount(line) -> Decimal:
    if line.catch_weight_enabled and line.prepared_weight is not None:
        return line.prepared_weight.value
    return line.prepared_quantity.value if line.prepared_quantity else Decimal("0")


class EvaluateCatchWeightUseCase(_OrdersDeliveryBaseUseCase):
    def __init__(self, authorization=None, *,
                 whatsapp_client: OrdersDeliveryWhatsAppClient | None = None) -> None:
        super().__init__(authorization)
        self._whatsapp = whatsapp_client or OrdersDeliveryWhatsAppClient()

    def execute(self, connection, *, order_id: str, line_id: str, tolerance_pct: Decimal,
                actor_user_id: str, operation_id: str,
                approval_expires_at: str | None = None) -> OrderResult:
        try:
            self._auth.require(actor_user_id, OrdersDeliveryPermissions.WEIGHT_CAPTURE)
        except OrdersDeliveryDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        with OrdersDeliveryUnitOfWork(connection) as uow:
            order = uow.orders.get(order_id)
            if order is None:
                return fail_from_domain_error(
                    OrderNotFoundError(f"Pedido {order_id} no existe"), operation_id=operation_id)
            line = next((l for l in order.lines if l.id == line_id), None)
            if line is None:
                return fail_from_domain_error(
                    OrderLineNotFoundError(f"Línea {line_id} no existe"), operation_id=operation_id)
            try:
                evaluation = CatchWeightAdjustmentPolicy.evaluate(
                    requested_amount=_line_requested_amount(line),
                    prepared_amount=_line_prepared_amount(line),
                    unit_price=line.unit_price_snapshot, tolerance_pct=tolerance_pct)
                order.apply_weight_evaluation(
                    line_id=line_id, evaluation=evaluation,
                    approval_expires_at=approval_expires_at)
            except OrdersDeliveryDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)

            uow.orders.save(order)
            if not evaluation.within_tolerance:
                self._emit(
                    uow, OrderEvents.CUSTOMER_APPROVAL_REQUIRED, aggregate_type="CustomerOrder",
                    entity_id=order.id, operation_id=operation_id, branch_id=order.branch_id,
                    actor_user_id=actor_user_id, line_id=line_id,
                    difference_pct=str(evaluation.difference_pct))
            else:
                self._emit(
                    uow, OrderEvents.ITEM_WEIGHT_ADJUSTED, aggregate_type="CustomerOrder",
                    entity_id=order.id, operation_id=operation_id, branch_id=order.branch_id,
                    actor_user_id=actor_user_id, line_id=line_id)

        notification_sent = False
        if not evaluation.within_tolerance:
            try:
                notification_sent = self._whatsapp.notify_customer_approval_required(
                    phone=order.contact_phone or "", order_number=order.order_number or order.id,
                    reason=f"ajuste de peso ({evaluation.difference_pct}% de diferencia)")
            except Exception as exc:  # noqa: BLE001 - never fail the evaluation over a notification
                logger.warning(
                    "Notificación de aprobación no enviada para pedido %s: %s", order.id, exc)
        return OrderResult.ok(
            "Ajuste de peso evaluado", entity_id=order.id, operation_id=operation_id,
            order=CustomerOrderDTO.from_entity(order),
            within_tolerance=evaluation.within_tolerance,
            proposed_subtotal=evaluation.proposed_subtotal,
            notification_sent=notification_sent)


class AcceptWeightAdjustmentUseCase(_OrdersDeliveryBaseUseCase):
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
                order.accept_customer_adjustment(line_id)
            except OrdersDeliveryDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.orders.save(order)
            self._emit(
                uow, OrderEvents.CUSTOMER_ADJUSTMENT_ACCEPTED, aggregate_type="CustomerOrder",
                entity_id=order.id, operation_id=operation_id, branch_id=order.branch_id,
                actor_user_id=actor_user_id, line_id=line_id)
        return OrderResult.ok(
            "Ajuste aceptado por el cliente", entity_id=order.id, operation_id=operation_id,
            order=CustomerOrderDTO.from_entity(order))


class RejectWeightAdjustmentUseCase(_OrdersDeliveryBaseUseCase):
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
                order.reject_customer_adjustment(line_id)
            except OrdersDeliveryDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.orders.save(order)
            self._emit(
                uow, OrderEvents.CUSTOMER_ADJUSTMENT_REJECTED, aggregate_type="CustomerOrder",
                entity_id=order.id, operation_id=operation_id, branch_id=order.branch_id,
                actor_user_id=actor_user_id, line_id=line_id)
        return OrderResult.ok(
            "Ajuste rechazado por el cliente", entity_id=order.id, operation_id=operation_id,
            order=CustomerOrderDTO.from_entity(order))


class OverrideWeightAdjustmentUseCase(_OrdersDeliveryBaseUseCase):
    """§65: a supervisor overrides an out-of-tolerance line without waiting
    for the customer — hot authorization, requester and authorizer must be
    distinct (`OrdersDeliverySegregationOfDutiesError` otherwise)."""

    def execute(
        self, connection, *, order_id: str, line_id: str, requested_by: str,
        authorizer_user_id: str, reason: str, operation_id: str,
    ) -> OrderResult:
        with OrdersDeliveryUnitOfWork(connection) as uow:
            order = uow.orders.get(order_id)
            if order is None:
                return fail_from_domain_error(
                    OrderNotFoundError(f"Pedido {order_id} no existe"), operation_id=operation_id)
            try:
                self._auth.authorize_exception(
                    authorizer_user_id=authorizer_user_id, requested_by=requested_by,
                    permission_code=OrdersDeliveryPermissions.WEIGHT_OVERRIDE,
                    operation_id=operation_id, reason=reason, order_id=order_id)
                order.accept_customer_adjustment(line_id)
            except OrdersDeliveryDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.orders.save(order)
            self._emit(
                uow, OrderEvents.CUSTOMER_ADJUSTMENT_ACCEPTED, aggregate_type="CustomerOrder",
                entity_id=order.id, operation_id=operation_id, branch_id=order.branch_id,
                actor_user_id=authorizer_user_id, line_id=line_id, override=True, reason=reason)
        return OrderResult.ok(
            "Ajuste de peso autorizado en caliente", entity_id=order.id,
            operation_id=operation_id, order=CustomerOrderDTO.from_entity(order))


class ExpireCustomerApprovalUseCase(_OrdersDeliveryBaseUseCase):
    """§27/ORD-11: a scheduler/cron calls this once the approval window
    passes with no customer response — every still-pending line is treated
    as implicitly rejected (never left dangling forever). Reuses
    `CUSTOMER_APPROVAL_OVERRIDE` (a system trigger, same reasoning ORD-6
    already applied to schedule activation)."""

    def execute(self, connection, *, order_id: str, actor_user_id: str, operation_id: str,
                now: datetime | None = None) -> OrderResult:
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
                order.expire_customer_approval(now=now or datetime.now(timezone.utc))
            except OrdersDeliveryDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.orders.save(order)
            self._emit(
                uow, OrderEvents.CUSTOMER_ADJUSTMENT_REJECTED, aggregate_type="CustomerOrder",
                entity_id=order.id, operation_id=operation_id, branch_id=order.branch_id,
                actor_user_id=actor_user_id, expired=True)
        return OrderResult.ok(
            "Aprobación del cliente expirada", entity_id=order.id, operation_id=operation_id,
            order=CustomerOrderDTO.from_entity(order))
