"""Cash-on-delivery use cases (master prompt §44-45). A `CashCollectionRequest`
is created explicitly (usually right after dispatch, when
`DeliveryJob.cash_to_collect > 0`) — never inferred silently — and later
resolved with what the driver actually collected. Reconciling MANY
collections into one driver's settlement is ORD-21's own aggregate.
"""

from __future__ import annotations

from decimal import Decimal

from backend.application.orders_delivery.audit import OrdersDeliveryAuditActions
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
from backend.domain.sales.enums import PaymentMethod
from backend.domain.sales.exceptions import (
    PaymentReferenceInvalidError,
    PaymentReferenceRequiredError,
)
from backend.domain.sales.policies.payment_policy import SalePaymentPolicy
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
            self._audit(
                uow, OrdersDeliveryAuditActions.CASH_COLLECTION_REQUESTED, entity="DriverCashCollection", entity_id=collection.id,
                branch_id=job.branch_id, actor_user_id=actor_user_id, operation_id=operation_id,
                delivery_job_id=job.id, expected_amount=str(collection.expected_amount))
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
            problema = _transfer_reference_problem(collection, collected_amount, reference)
            if problema is not None:
                return OrderResult.fail(*problema, operation_id=operation_id)
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
                    collection_id=collection.id, status=collection.status.value,
                    driver_id=collection.driver_id,
                    payment_method=collection.payment_method.value,
                    collected_amount=str(collection.collected_amount))
        return OrderResult.ok(
            "Cobro registrado", entity_id=collection.id, operation_id=operation_id,
            status=collection.status.value)


def _transfer_reference_problem(collection, collected_amount, reference):
    """Un cobro por transferencia lleva su referencia (decisión 2026-11-14): la
    misma validación de Ventas (SDLC-PAY-002), no una segunda. Un intento fallido
    (monto 0) no la necesita. Devuelve `(mensaje, código)` o None."""
    if collection.payment_method != CollectionPaymentMethod.TRANSFER:
        return None
    if Decimal(str(collected_amount)) <= 0:
        return None
    try:
        SalePaymentPolicy.ensure_reference_valid(
            method=PaymentMethod.TRANSFER, reference=reference)
    except PaymentReferenceRequiredError as exc:
        return str(exc), "PAYMENT_REFERENCE_REQUIRED"
    except PaymentReferenceInvalidError as exc:
        return str(exc), "PAYMENT_REFERENCE_INVALID"
    return None
