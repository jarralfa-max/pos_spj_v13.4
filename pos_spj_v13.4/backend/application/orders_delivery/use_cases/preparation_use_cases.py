"""Preparation use cases (master prompt §25): assign, start, record a
prepared line, complete. Gated by the `PREPARATION_*`/`WEIGHT_CAPTURE`
permissions ORD-1 already defined for exactly this area.
"""

from __future__ import annotations

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
from backend.domain.orders_delivery.value_objects.order_quantity import OrderQuantity
from backend.infrastructure.db.repositories.orders_delivery.unit_of_work import (
    OrdersDeliveryUnitOfWork,
)


class AssignPreparationUseCase(_OrdersDeliveryBaseUseCase):
    def execute(self, connection, *, order_id: str, assigned_to_user_id: str,
                actor_user_id: str, operation_id: str,
                station_id: str | None = None) -> OrderResult:
        try:
            self._auth.require(actor_user_id, OrdersDeliveryPermissions.PREPARATION_ASSIGN)
        except OrdersDeliveryDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        with OrdersDeliveryUnitOfWork(connection) as uow:
            order = uow.orders.get(order_id)
            if order is None:
                return fail_from_domain_error(
                    OrderNotFoundError(f"Pedido {order_id} no existe"), operation_id=operation_id)
            try:
                order.assign_preparation(assigned_to_user_id=assigned_to_user_id,
                                          station_id=station_id)
            except OrdersDeliveryDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.orders.save(order)
        return OrderResult.ok(
            "Preparación asignada", entity_id=order.id, operation_id=operation_id,
            order=CustomerOrderDTO.from_entity(order))


class StartPreparationUseCase(_OrdersDeliveryBaseUseCase):
    def execute(self, connection, *, order_id: str, actor_user_id: str,
                operation_id: str) -> OrderResult:
        try:
            self._auth.require(actor_user_id, OrdersDeliveryPermissions.PREPARATION_START)
        except OrdersDeliveryDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        with OrdersDeliveryUnitOfWork(connection) as uow:
            order = uow.orders.get(order_id)
            if order is None:
                return fail_from_domain_error(
                    OrderNotFoundError(f"Pedido {order_id} no existe"), operation_id=operation_id)
            try:
                order.start_preparation()
            except OrdersDeliveryDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.orders.save(order)
            self._emit(
                uow, OrderEvents.PREPARATION_STARTED, aggregate_type="CustomerOrder",
                entity_id=order.id, operation_id=operation_id, branch_id=order.branch_id,
                actor_user_id=actor_user_id)
        return OrderResult.ok(
            "Preparación iniciada", entity_id=order.id, operation_id=operation_id,
            order=CustomerOrderDTO.from_entity(order))


class RecordPreparedLineUseCase(_OrdersDeliveryBaseUseCase):
    def execute(
        self, connection, *, order_id: str, line_id: str, actor_user_id: str,
        operation_id: str, quantity: str | None = None, quantity_unit: str = "PZA",
        weight: str | None = None, weight_unit: str = "KG",
    ) -> OrderResult:
        try:
            self._auth.require(actor_user_id, OrdersDeliveryPermissions.WEIGHT_CAPTURE)
        except OrdersDeliveryDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        with OrdersDeliveryUnitOfWork(connection) as uow:
            order = uow.orders.get(order_id)
            if order is None:
                return fail_from_domain_error(
                    OrderNotFoundError(f"Pedido {order_id} no existe"), operation_id=operation_id)
            line = next((line for line in order.lines if line.id == line_id), None)
            if line is None:
                return fail_from_domain_error(
                    OrderLineNotFoundError(f"Línea {line_id} no existe"), operation_id=operation_id)
            try:
                line.record_prepared_amount(
                    quantity=OrderQuantity(quantity, unit=quantity_unit) if quantity else None,
                    weight=OrderQuantity(weight, unit=weight_unit) if weight else None,
                )
            except OrdersDeliveryDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.orders.save(order)
        return OrderResult.ok(
            "Cantidad preparada registrada", entity_id=order.id, operation_id=operation_id,
            order=CustomerOrderDTO.from_entity(order))


class CompletePreparationUseCase(_OrdersDeliveryBaseUseCase):
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
            try:
                order.complete_preparation()
            except OrdersDeliveryDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.orders.save(order)
            self._emit(
                uow, OrderEvents.READY, aggregate_type="CustomerOrder", entity_id=order.id,
                operation_id=operation_id, branch_id=order.branch_id, actor_user_id=actor_user_id)
        return OrderResult.ok(
            "Pedido listo", entity_id=order.id, operation_id=operation_id,
            order=CustomerOrderDTO.from_entity(order))
