"""DeliveryJob use cases (master prompt §31-32): create, assign driver. The
first real callers of the SEPARATE `DeliveryJob` aggregate — dispatch,
tracking, delivery confirmation and failure (§32's remaining transitions)
are ORD-16-19's use cases, reusing this same aggregate/repository.

`CreateDeliveryJobUseCase` only applies to orders whose `fulfillment_type`
actually needs a delivery job (master prompt §30: "No crear un DeliveryJob
para pickup") — the caller is responsible for not calling this for
COUNTER/PICKUP orders; the use case itself does not re-derive that policy
from `CustomerOrder` to avoid a circular dependency between the two
aggregates (§5: DeliveryJob references `order_id`, never the reverse).
"""

from __future__ import annotations

from decimal import Decimal

from backend.application.orders_delivery.dto import DeliveryJobDTO
from backend.application.orders_delivery.permissions import OrdersDeliveryPermissions
from backend.application.orders_delivery.result import OrderResult, fail_from_domain_error
from backend.application.orders_delivery.use_cases._base import _OrdersDeliveryBaseUseCase
from backend.domain.orders_delivery.delivery_job import DeliveryJob
from backend.domain.orders_delivery.events import DeliveryEvents
from backend.domain.orders_delivery.exceptions import DeliveryJobNotFoundError, OrdersDeliveryDomainError
from backend.infrastructure.db.repositories.orders_delivery.unit_of_work import (
    OrdersDeliveryUnitOfWork,
)


class CreateDeliveryJobUseCase(_OrdersDeliveryBaseUseCase):
    def execute(
        self, connection, *, order_id: str, branch_id: str, actor_user_id: str,
        operation_id: str, delivery_zone_id: str | None = None, priority: str | None = None,
        scheduled_window_start: str | None = None, scheduled_window_end: str | None = None,
        delivery_fee: Decimal = Decimal("0"), cash_to_collect: Decimal = Decimal("0"),
        payment_method_expected: str | None = None,
    ) -> OrderResult:
        try:
            self._auth.require(actor_user_id, OrdersDeliveryPermissions.DELIVERY_CREATE)
        except OrdersDeliveryDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        with OrdersDeliveryUnitOfWork(connection) as uow:
            existing = uow.delivery_jobs.find_by_operation_id(operation_id)
            if existing is not None:
                return OrderResult.ok(
                    "Job de entrega ya existente (idempotente)", entity_id=existing.id,
                    operation_id=operation_id, delivery_job=DeliveryJobDTO.from_entity(existing))
            try:
                job = DeliveryJob.create(
                    order_id=order_id, branch_id=branch_id, operation_id=operation_id,
                    delivery_zone_id=delivery_zone_id, priority=priority,
                    scheduled_window_start=scheduled_window_start,
                    scheduled_window_end=scheduled_window_end, delivery_fee=delivery_fee,
                    cash_to_collect=cash_to_collect,
                    payment_method_expected=payment_method_expected)
            except OrdersDeliveryDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.delivery_jobs.save(job)
            self._emit_delivery(
                uow, DeliveryEvents.JOB_CREATED, entity_id=job.id, operation_id=operation_id,
                branch_id=job.branch_id, actor_user_id=actor_user_id, order_id=order_id)
        return OrderResult.ok(
            "Job de entrega creado", entity_id=job.id, operation_id=operation_id,
            delivery_job=DeliveryJobDTO.from_entity(job))


class AssignDriverUseCase(_OrdersDeliveryBaseUseCase):
    def execute(self, connection, *, delivery_job_id: str, driver_id: str, actor_user_id: str,
                operation_id: str) -> OrderResult:
        try:
            self._auth.require(actor_user_id, OrdersDeliveryPermissions.DRIVER_ASSIGN)
        except OrdersDeliveryDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        with OrdersDeliveryUnitOfWork(connection) as uow:
            job = uow.delivery_jobs.get(delivery_job_id)
            if job is None:
                return fail_from_domain_error(
                    DeliveryJobNotFoundError(f"Job de entrega {delivery_job_id} no existe"),
                    operation_id=operation_id)
            try:
                job.assign_driver(driver_id=driver_id)
            except OrdersDeliveryDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.delivery_jobs.save(job)
            self._emit_delivery(
                uow, DeliveryEvents.DRIVER_ASSIGNED, entity_id=job.id, operation_id=operation_id,
                branch_id=job.branch_id, actor_user_id=actor_user_id, driver_id=driver_id)
        return OrderResult.ok(
            "Repartidor asignado", entity_id=job.id, operation_id=operation_id,
            delivery_job=DeliveryJobDTO.from_entity(job))
