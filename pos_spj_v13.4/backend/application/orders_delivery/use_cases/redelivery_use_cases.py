"""Failed delivery, redelivery and return-to-branch use cases (master
prompt §40-41). A redelivery ALWAYS spins up a genuinely NEW `DeliveryJob`
(never reuses/re-dispatches the failed one) — the original job stays
`REDELIVERY_PENDING` permanently as the historical record of what failed;
`RedeliveryRequest.new_delivery_job_id` is what the second attempt is
tracked under. Never reuses the same failed attempt silently.
"""

from __future__ import annotations

from decimal import Decimal

from backend.application.orders_delivery.dto import DeliveryJobDTO
from backend.application.orders_delivery.permissions import OrdersDeliveryPermissions
from backend.application.orders_delivery.result import OrderResult, fail_from_domain_error
from backend.application.orders_delivery.use_cases._base import _OrdersDeliveryBaseUseCase
from backend.domain.orders_delivery.delivery_job import DeliveryJob
from backend.domain.orders_delivery.enums import DeliveryStatus
from backend.domain.orders_delivery.events import DeliveryEvents
from backend.domain.orders_delivery.exceptions import (
    DeliveryJobNotFoundError,
    OrdersDeliveryDomainError,
    RedeliveryNotAllowedError,
    RedeliveryRequestNotFoundError,
)
from backend.domain.orders_delivery.redelivery import RedeliveryRequest
from backend.infrastructure.db.repositories.orders_delivery.unit_of_work import (
    OrdersDeliveryUnitOfWork,
)


class RequestRedeliveryUseCase(_OrdersDeliveryBaseUseCase):
    def execute(
        self, connection, *, delivery_job_id: str, reason: str, actor_user_id: str,
        operation_id: str, new_window_start: str | None = None,
        new_window_end: str | None = None, additional_fee: Decimal = Decimal("0"),
    ) -> OrderResult:
        try:
            self._auth.require(actor_user_id, OrdersDeliveryPermissions.REDELIVERY_REQUEST)
        except OrdersDeliveryDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        with OrdersDeliveryUnitOfWork(connection) as uow:
            job = uow.delivery_jobs.get(delivery_job_id)
            if job is None:
                return fail_from_domain_error(
                    DeliveryJobNotFoundError(f"Job de entrega {delivery_job_id} no existe"),
                    operation_id=operation_id)
            if job.status != DeliveryStatus.FAILED:
                return fail_from_domain_error(
                    RedeliveryNotAllowedError(
                        f"Solo se puede solicitar reentrega desde un job fallido "
                        f"(estado actual: {job.status.value})"),
                    operation_id=operation_id)
            try:
                request = RedeliveryRequest.create(
                    original_delivery_job_id=delivery_job_id, reason=reason,
                    requested_by_user_id=actor_user_id, new_window_start=new_window_start,
                    new_window_end=new_window_end, additional_fee=additional_fee)
                job.request_redelivery()
            except OrdersDeliveryDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.redeliveries.save(request)
            uow.delivery_jobs.save(job)
        return OrderResult.ok(
            "Reentrega solicitada", entity_id=request.id, operation_id=operation_id)


class ApproveRedeliveryUseCase(_OrdersDeliveryBaseUseCase):
    def execute(self, connection, *, redelivery_request_id: str, actor_user_id: str,
                operation_id: str) -> OrderResult:
        try:
            self._auth.require(actor_user_id, OrdersDeliveryPermissions.REDELIVERY_REQUEST)
        except OrdersDeliveryDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        with OrdersDeliveryUnitOfWork(connection) as uow:
            request = uow.redeliveries.get(redelivery_request_id)
            if request is None:
                return fail_from_domain_error(
                    RedeliveryRequestNotFoundError(
                        f"Solicitud de reentrega {redelivery_request_id} no existe"),
                    operation_id=operation_id)
            original_job = uow.delivery_jobs.get(request.original_delivery_job_id)
            if original_job is None:
                return fail_from_domain_error(
                    DeliveryJobNotFoundError(
                        f"Job de entrega {request.original_delivery_job_id} no existe"),
                    operation_id=operation_id)
            try:
                new_job = DeliveryJob.create(
                    order_id=original_job.order_id, branch_id=original_job.branch_id,
                    operation_id=operation_id, delivery_zone_id=original_job.delivery_zone_id,
                    scheduled_window_start=request.new_window_start,
                    scheduled_window_end=request.new_window_end,
                    delivery_fee=request.additional_fee,
                    cash_to_collect=original_job.cash_to_collect,
                    payment_method_expected=original_job.payment_method_expected)
                request.approve(approved_by_user_id=actor_user_id, new_delivery_job_id=new_job.id)
            except OrdersDeliveryDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.delivery_jobs.save(new_job)
            uow.redeliveries.save(request)
            self._emit_delivery(
                uow, DeliveryEvents.REDELIVERY_REQUESTED, entity_id=new_job.id,
                operation_id=operation_id, branch_id=new_job.branch_id,
                actor_user_id=actor_user_id, original_delivery_job_id=original_job.id)
        return OrderResult.ok(
            "Reentrega aprobada", entity_id=new_job.id, operation_id=operation_id,
            delivery_job=DeliveryJobDTO.from_entity(new_job))


class RejectRedeliveryUseCase(_OrdersDeliveryBaseUseCase):
    def execute(self, connection, *, redelivery_request_id: str, actor_user_id: str,
                operation_id: str) -> OrderResult:
        try:
            self._auth.require(actor_user_id, OrdersDeliveryPermissions.REDELIVERY_REQUEST)
        except OrdersDeliveryDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        with OrdersDeliveryUnitOfWork(connection) as uow:
            request = uow.redeliveries.get(redelivery_request_id)
            if request is None:
                return fail_from_domain_error(
                    RedeliveryRequestNotFoundError(
                        f"Solicitud de reentrega {redelivery_request_id} no existe"),
                    operation_id=operation_id)
            try:
                request.reject()
            except OrdersDeliveryDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.redeliveries.save(request)
        return OrderResult.ok(
            "Reentrega rechazada", entity_id=request.id, operation_id=operation_id)


class ReturnToBranchUseCase(_OrdersDeliveryBaseUseCase):
    def execute(self, connection, *, delivery_job_id: str, actor_user_id: str,
                operation_id: str) -> OrderResult:
        try:
            self._auth.require(actor_user_id, OrdersDeliveryPermissions.RETURN_TO_BRANCH)
        except OrdersDeliveryDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        with OrdersDeliveryUnitOfWork(connection) as uow:
            job = uow.delivery_jobs.get(delivery_job_id)
            if job is None:
                return fail_from_domain_error(
                    DeliveryJobNotFoundError(f"Job de entrega {delivery_job_id} no existe"),
                    operation_id=operation_id)
            try:
                job.start_return()
                job.complete_return()
            except OrdersDeliveryDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.delivery_jobs.save(job)
            self._emit_delivery(
                uow, DeliveryEvents.RETURNED_TO_BRANCH, entity_id=job.id,
                operation_id=operation_id, branch_id=job.branch_id, actor_user_id=actor_user_id)
        return OrderResult.ok(
            "Pedido regresado a sucursal", entity_id=job.id, operation_id=operation_id,
            delivery_job=DeliveryJobDTO.from_entity(job))
