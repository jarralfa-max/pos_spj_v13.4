"""Scheduled order use cases (master prompt §19). `ScheduleOrderUseCase`/
`RescheduleOrderUseCase` are gated by the same `ORDER_SCHEDULE`/
`ORDER_RESCHEDULE` permissions the order itself already exposes;
`ActivateScheduledOrderUseCase` is the one a future scheduler/cron job calls
(§19: "La activación debe considerar anticipación... horario de sucursal" —
that cross-context evaluation is NOT built here, only the state-transition
mechanics `CustomerOrder.activate_schedule()` already validates).
"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.application.orders_delivery.dto import CustomerOrderDTO
from backend.application.orders_delivery.permissions import OrdersDeliveryPermissions
from backend.application.orders_delivery.result import OrderResult, fail_from_domain_error
from backend.application.orders_delivery.use_cases._base import _OrdersDeliveryBaseUseCase
from backend.domain.orders_delivery.events import OrderEvents
from backend.domain.orders_delivery.exceptions import OrderNotFoundError, OrdersDeliveryDomainError
from backend.infrastructure.db.repositories.orders_delivery.unit_of_work import (
    OrdersDeliveryUnitOfWork,
)


class ScheduleOrderUseCase(_OrdersDeliveryBaseUseCase):
    def execute(
        self, connection, *, order_id: str, scheduled_for: str, window_start: str,
        window_end: str, activation_at: str, actor_user_id: str, operation_id: str,
    ) -> OrderResult:
        try:
            self._auth.require(actor_user_id, OrdersDeliveryPermissions.ORDER_SCHEDULE)
        except OrdersDeliveryDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        with OrdersDeliveryUnitOfWork(connection) as uow:
            order = uow.orders.get(order_id)
            if order is None:
                return fail_from_domain_error(
                    OrderNotFoundError(f"Pedido {order_id} no existe"), operation_id=operation_id)
            try:
                order.schedule(scheduled_for=scheduled_for, window_start=window_start,
                                window_end=window_end, activation_at=activation_at)
            except OrdersDeliveryDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.orders.save(order)
            self._emit(
                uow, OrderEvents.SCHEDULED, aggregate_type="CustomerOrder", entity_id=order.id,
                operation_id=operation_id, branch_id=order.branch_id, actor_user_id=actor_user_id)
        return OrderResult.ok(
            "Pedido programado", entity_id=order.id, operation_id=operation_id,
            order=CustomerOrderDTO.from_entity(order))


class RescheduleOrderUseCase(_OrdersDeliveryBaseUseCase):
    def execute(
        self, connection, *, order_id: str, scheduled_for: str, window_start: str,
        window_end: str, activation_at: str, actor_user_id: str, operation_id: str,
    ) -> OrderResult:
        try:
            self._auth.require(actor_user_id, OrdersDeliveryPermissions.ORDER_RESCHEDULE)
        except OrdersDeliveryDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        with OrdersDeliveryUnitOfWork(connection) as uow:
            order = uow.orders.get(order_id)
            if order is None:
                return fail_from_domain_error(
                    OrderNotFoundError(f"Pedido {order_id} no existe"), operation_id=operation_id)
            try:
                order.reschedule(scheduled_for=scheduled_for, window_start=window_start,
                                  window_end=window_end, activation_at=activation_at)
            except OrdersDeliveryDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.orders.save(order)
        return OrderResult.ok(
            "Pedido reprogramado", entity_id=order.id, operation_id=operation_id,
            order=CustomerOrderDTO.from_entity(order))


class ActivateScheduledOrderUseCase(_OrdersDeliveryBaseUseCase):
    def execute(self, connection, *, order_id: str, actor_user_id: str, operation_id: str,
                now: datetime | None = None) -> OrderResult:
        try:
            self._auth.require(actor_user_id, OrdersDeliveryPermissions.ORDER_SCHEDULE)
        except OrdersDeliveryDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        with OrdersDeliveryUnitOfWork(connection) as uow:
            order = uow.orders.get(order_id)
            if order is None:
                return fail_from_domain_error(
                    OrderNotFoundError(f"Pedido {order_id} no existe"), operation_id=operation_id)
            try:
                order.activate_schedule(now=now or datetime.now(timezone.utc))
            except OrdersDeliveryDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.orders.save(order)
            self._emit(
                uow, OrderEvents.SCHEDULE_ACTIVATED, aggregate_type="CustomerOrder",
                entity_id=order.id, operation_id=operation_id, branch_id=order.branch_id,
                actor_user_id=actor_user_id)
        return OrderResult.ok(
            "Programación activada", entity_id=order.id, operation_id=operation_id,
            order=CustomerOrderDTO.from_entity(order))
