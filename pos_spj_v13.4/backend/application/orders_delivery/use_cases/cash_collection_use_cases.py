"""Cash-on-delivery use cases (master prompt §44-45). A `CashCollectionRequest`
is created explicitly (usually right after dispatch, when
`DeliveryJob.cash_to_collect > 0`) — never inferred silently — and later
resolved with what the driver actually collected. Reconciling MANY
collections into one driver's settlement is ORD-21's own aggregate.
"""

from __future__ import annotations

from decimal import Decimal

from backend.application.orders_delivery.permissions import OrdersDeliveryPermissions
from backend.application.orders_delivery.result import OrderResult, fail_from_domain_error
from backend.application.orders_delivery.use_cases._base import _OrdersDeliveryBaseUseCase
from backend.domain.orders_delivery.cash_collection import DriverCashCollection
from backend.domain.orders_delivery.enums import CollectionPaymentMethod
from backend.domain.orders_delivery.events import DeliveryEvents
from backend.domain.orders_delivery.exceptions import (
    CashCollectionNotFoundError,
    DeliveryJobNotFoundError,
    OrdersDeliveryDomainError,
)
from backend.infrastructure.db.repositories.orders_delivery.unit_of_work import (
    OrdersDeliveryUnitOfWork,
)


class CreateCashCollectionRequestUseCase(_OrdersDeliveryBaseUseCase):
    def execute(
        self, connection, *, delivery_job_id: str, payment_method: CollectionPaymentMethod | str,
        actor_user_id: str, operation_id: str,
    ) -> OrderResult:
        try:
            self._auth.require(actor_user_id, OrdersDeliveryPermissions.CASH_COLLECTION_RECORD)
        except OrdersDeliveryDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        payment_method = (payment_method if isinstance(payment_method, CollectionPaymentMethod)
                           else CollectionPaymentMethod(payment_method))
        with OrdersDeliveryUnitOfWork(connection) as uow:
            job = uow.delivery_jobs.get(delivery_job_id)
            if job is None:
                return fail_from_domain_error(
                    DeliveryJobNotFoundError(f"Job de entrega {delivery_job_id} no existe"),
                    operation_id=operation_id)
            existing = uow.cash_collections.get_by_job_id(delivery_job_id)
            if existing is not None:
                return OrderResult.ok(
                    "Solicitud de cobro ya existente (idempotente)", entity_id=existing.id,
                    operation_id=operation_id)
            if not job.assigned_driver_id:
                return fail_from_domain_error(
                    DeliveryJobNotFoundError(
                        "No se puede solicitar cobro sin repartidor asignado"),
                    operation_id=operation_id)
            try:
                collection = DriverCashCollection.create(
                    delivery_job_id=delivery_job_id, driver_id=job.assigned_driver_id,
                    expected_amount=job.cash_to_collect, payment_method=payment_method)
            except OrdersDeliveryDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.cash_collections.save(collection)
        return OrderResult.ok(
            "Solicitud de cobro creada", entity_id=collection.id, operation_id=operation_id)


class RecordCashCollectionUseCase(_OrdersDeliveryBaseUseCase):
    def execute(
        self, connection, *, collection_id: str, collected_amount: Decimal, actor_user_id: str,
        operation_id: str, reference: str | None = None,
    ) -> OrderResult:
        try:
            self._auth.require(actor_user_id, OrdersDeliveryPermissions.CASH_COLLECTION_RECORD)
        except OrdersDeliveryDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        with OrdersDeliveryUnitOfWork(connection) as uow:
            collection = uow.cash_collections.get(collection_id)
            if collection is None:
                return fail_from_domain_error(
                    CashCollectionNotFoundError(f"Cobro {collection_id} no existe"),
                    operation_id=operation_id)
            try:
                collection.record_collection(collected_amount=collected_amount, reference=reference)
            except OrdersDeliveryDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            job = uow.delivery_jobs.get(collection.delivery_job_id)
            uow.cash_collections.save(collection)
            if job is not None:
                self._emit_delivery(
                    uow, DeliveryEvents.CASH_COLLECTION_RECORDED,
                    entity_id=collection.delivery_job_id, operation_id=operation_id,
                    branch_id=job.branch_id, actor_user_id=actor_user_id,
                    collection_id=collection.id, status=collection.status.value)
        return OrderResult.ok(
            "Cobro registrado", entity_id=collection.id, operation_id=operation_id,
            status=collection.status.value)
