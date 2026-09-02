"""Dispatch and delivery use cases (master prompt §36-40). These orchestrate
BOTH aggregates (`CustomerOrder` and `DeliveryJob`) in one transaction — the
aggregates themselves never reference each other (§5), only the use case
layer coordinates them.
"""

from __future__ import annotations

import logging

from backend.application.orders_delivery.dto import CustomerOrderDTO, DeliveryJobDTO
from backend.application.orders_delivery.permissions import OrdersDeliveryPermissions
from backend.application.orders_delivery.result import OrderResult, fail_from_domain_error
from backend.application.orders_delivery.use_cases._base import _OrdersDeliveryBaseUseCase
from backend.domain.orders_delivery.delivery_job import DeliveryAttempt
from backend.domain.orders_delivery.events import DeliveryEvents
from backend.domain.orders_delivery.exceptions import (
    DeliveryJobNotFoundError,
    OrderNotFoundError,
    OrdersDeliveryDomainError,
)
from backend.domain.orders_delivery.policies.dispatch_policy import DispatchPolicy
from backend.domain.orders_delivery.policies.notification_policy import DeliveryNotificationPolicy
from backend.domain.orders_delivery.value_objects.delivery_evidence import DeliveryEvidence
from backend.infrastructure.db.repositories.orders_delivery.unit_of_work import (
    OrdersDeliveryUnitOfWork,
)
from backend.infrastructure.integrations.orders_delivery_internal_notifier import (
    OrdersDeliveryInternalNotifier,
)
from backend.infrastructure.integrations.orders_delivery_whatsapp_client import (
    OrdersDeliveryWhatsAppClient,
)

logger = logging.getLogger("spj.orders_delivery.dispatch")


def _notify_customer(whatsapp: OrdersDeliveryWhatsAppClient, order, event_name: str) -> bool:
    message = DeliveryNotificationPolicy.customer_message(
        event_name, order_number=order.order_number or order.id)
    if message is None:
        return False
    try:
        return whatsapp.send_message(phone=order.contact_phone or "", message=message)
    except Exception as exc:  # noqa: BLE001 - never fail the operation over a notification
        logger.warning("Notificación de cliente no enviada para pedido %s: %s", order.id, exc)
        return False


class DispatchDeliveryJobUseCase(_OrdersDeliveryBaseUseCase):
    def __init__(self, authorization=None, *,
                 whatsapp_client: OrdersDeliveryWhatsAppClient | None = None) -> None:
        super().__init__(authorization)
        self._whatsapp = whatsapp_client or OrdersDeliveryWhatsAppClient()

    def execute(self, connection, *, delivery_job_id: str, actor_user_id: str,
                operation_id: str) -> OrderResult:
        try:
            self._auth.require(actor_user_id, OrdersDeliveryPermissions.DISPATCH)
        except OrdersDeliveryDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        with OrdersDeliveryUnitOfWork(connection) as uow:
            job = uow.delivery_jobs.get(delivery_job_id)
            if job is None:
                return fail_from_domain_error(
                    DeliveryJobNotFoundError(f"Job de entrega {delivery_job_id} no existe"),
                    operation_id=operation_id)
            order = uow.orders.get(job.order_id)
            if order is None:
                return fail_from_domain_error(
                    OrderNotFoundError(f"Pedido {job.order_id} no existe"),
                    operation_id=operation_id)
            try:
                DispatchPolicy.ensure_can_dispatch(
                    fulfillment_status=order.fulfillment_status,
                    customer_approval_status=order.customer_approval_status,
                    has_assigned_driver=bool(job.assigned_driver_id))
                job.mark_ready_to_dispatch()
                job.dispatch()
                order.mark_dispatched()
            except OrdersDeliveryDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.delivery_jobs.save(job)
            uow.orders.save(order)
            self._emit_delivery(
                uow, DeliveryEvents.DISPATCHED, entity_id=job.id, operation_id=operation_id,
                branch_id=job.branch_id, actor_user_id=actor_user_id, order_id=order.id)

        notification_sent = _notify_customer(self._whatsapp, order, DeliveryEvents.DISPATCHED)
        return OrderResult.ok(
            "Pedido despachado", entity_id=job.id, operation_id=operation_id,
            delivery_job=DeliveryJobDTO.from_entity(job), order=CustomerOrderDTO.from_entity(order),
            notification_sent=notification_sent)


class MarkInTransitUseCase(_OrdersDeliveryBaseUseCase):
    def execute(self, connection, *, delivery_job_id: str, actor_user_id: str,
                operation_id: str) -> OrderResult:
        try:
            self._auth.require(actor_user_id, OrdersDeliveryPermissions.DELIVERY_VIEW)
        except OrdersDeliveryDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        with OrdersDeliveryUnitOfWork(connection) as uow:
            job = uow.delivery_jobs.get(delivery_job_id)
            if job is None:
                return fail_from_domain_error(
                    DeliveryJobNotFoundError(f"Job de entrega {delivery_job_id} no existe"),
                    operation_id=operation_id)
            try:
                job.mark_in_transit()
            except OrdersDeliveryDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.delivery_jobs.save(job)
            self._emit_delivery(
                uow, DeliveryEvents.OUT_FOR_DELIVERY, entity_id=job.id, operation_id=operation_id,
                branch_id=job.branch_id, actor_user_id=actor_user_id)
        return OrderResult.ok(
            "Pedido en tránsito", entity_id=job.id, operation_id=operation_id,
            delivery_job=DeliveryJobDTO.from_entity(job))


class ConfirmArrivalUseCase(_OrdersDeliveryBaseUseCase):
    def execute(self, connection, *, delivery_job_id: str, actor_user_id: str,
                operation_id: str) -> OrderResult:
        try:
            self._auth.require(actor_user_id, OrdersDeliveryPermissions.ARRIVAL_CONFIRM)
        except OrdersDeliveryDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        with OrdersDeliveryUnitOfWork(connection) as uow:
            job = uow.delivery_jobs.get(delivery_job_id)
            if job is None:
                return fail_from_domain_error(
                    DeliveryJobNotFoundError(f"Job de entrega {delivery_job_id} no existe"),
                    operation_id=operation_id)
            try:
                job.mark_arrived()
            except OrdersDeliveryDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.delivery_jobs.save(job)
            self._emit_delivery(
                uow, DeliveryEvents.ARRIVED, entity_id=job.id, operation_id=operation_id,
                branch_id=job.branch_id, actor_user_id=actor_user_id)
        return OrderResult.ok(
            "Llegada confirmada", entity_id=job.id, operation_id=operation_id,
            delivery_job=DeliveryJobDTO.from_entity(job))


class RecordDeliveryAttemptUseCase(_OrdersDeliveryBaseUseCase):
    """§38-40: records one delivery attempt (success or failure) and
    resolves both aggregates — `DeliveryJob.status` (via `record_attempt`)
    and, on success, `CustomerOrder.complete_delivery()`. A failed attempt
    does NOT complete the order — failed-delivery/redelivery handling is
    ORD-19's own use cases, working from `DeliveryJob.status == FAILED`.
    """

    def __init__(self, authorization=None, *,
                 whatsapp_client: OrdersDeliveryWhatsAppClient | None = None,
                 internal_notifier_factory=OrdersDeliveryInternalNotifier) -> None:
        super().__init__(authorization)
        self._whatsapp = whatsapp_client or OrdersDeliveryWhatsAppClient()
        self._internal_notifier_factory = internal_notifier_factory

    def execute(
        self, connection, *, delivery_job_id: str, successful: bool, actor_user_id: str,
        operation_id: str, recipient_name: str | None = None,
        signature_reference: str | None = None, photo_reference: str | None = None,
        pin_verified: bool = False, latitude: float | None = None,
        longitude: float | None = None, notes: str | None = None,
        failure_reason: str | None = None,
    ) -> OrderResult:
        try:
            self._auth.require(actor_user_id, OrdersDeliveryPermissions.DELIVERY_CONFIRM)
        except OrdersDeliveryDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        with OrdersDeliveryUnitOfWork(connection) as uow:
            job = uow.delivery_jobs.get(delivery_job_id)
            if job is None:
                return fail_from_domain_error(
                    DeliveryJobNotFoundError(f"Job de entrega {delivery_job_id} no existe"),
                    operation_id=operation_id)
            order = uow.orders.get(job.order_id)
            if order is None:
                return fail_from_domain_error(
                    OrderNotFoundError(f"Pedido {job.order_id} no existe"),
                    operation_id=operation_id)
            evidence = DeliveryEvidence(
                recipient_name=recipient_name, signature_reference=signature_reference,
                photo_reference=photo_reference, pin_verified=pin_verified,
                latitude=latitude, longitude=longitude, notes=notes,
            ) if successful else None
            try:
                attempt = DeliveryAttempt.create(
                    delivery_job_id=job.id, successful=successful, evidence=evidence,
                    failure_reason=failure_reason)
                job.start_delivery_attempt()
                job.record_attempt(attempt)
                if successful:
                    order.complete_delivery()
            except OrdersDeliveryDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.delivery_jobs.save(job)
            uow.orders.save(order)
            self._emit_delivery(
                uow, DeliveryEvents.COMPLETED if successful else DeliveryEvents.FAILED,
                entity_id=job.id, operation_id=operation_id, branch_id=job.branch_id,
                actor_user_id=actor_user_id)
        event_name = DeliveryEvents.COMPLETED if successful else DeliveryEvents.FAILED
        notification_sent = _notify_customer(self._whatsapp, order, event_name)
        if not successful and DeliveryNotificationPolicy.requires_internal_alert(event_name):
            try:
                self._internal_notifier_factory(connection).notify_roles(
                    roles=("admin", "gerente"), branch_id=job.branch_id,
                    tipo="entrega_fallida",
                    titulo=f"Entrega fallida — pedido {order.order_number or order.id}",
                    cuerpo=failure_reason or "Sin motivo especificado",
                    datos={"delivery_job_id": job.id, "order_id": order.id})
            except Exception as exc:  # noqa: BLE001 - never fail the attempt over an alert
                logger.warning("Alerta interna no enviada para job %s: %s", job.id, exc)
        return OrderResult.ok(
            "Intento de entrega registrado", entity_id=job.id, operation_id=operation_id,
            delivery_job=DeliveryJobDTO.from_entity(job),
            order=CustomerOrderDTO.from_entity(order), successful=successful,
            notification_sent=notification_sent)
