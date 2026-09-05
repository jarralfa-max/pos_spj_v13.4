"""Notification use cases (PROC-20, §20/§60): Procesamiento requests an alert
be delivered (WhatsApp or otherwise); it never sends one directly — same
Port+Null boundary as Calidad (PROC-16) and Mermas (PROC-15). Idempotent on
the caller-supplied ``operation_id`` via the processed-events registry, the
same mechanism composite multi-entity use cases use (PROC-11/15) — a single
alert must never be dispatched twice for the same triggering event.
"""

from __future__ import annotations

import json

from backend.application.meat_processing.authorization import MeatProcessingAuthorizationPolicy
from backend.application.meat_processing.permissions import MeatProcessingPermissions
from backend.application.meat_processing.ports import NotificationPort, NullNotificationPort
from backend.application.meat_processing.result import MeatProcessingResult
from backend.application.meat_processing.use_cases._shared import fail as _fail
from backend.domain.meat_processing.events import MeatProcessingEvents, build_meat_processing_event
from backend.domain.meat_processing.exceptions import (
    MeatProcessingError,
    MeatProcessingPermissionDeniedError,
    MeatProcessingScopeError,
)
from backend.infrastructure.db.repositories.meat_processing.unit_of_work import (
    MeatProcessingUnitOfWork,
)
from backend.shared.ids import new_uuid

_VALID_SEVERITIES = ("INFO", "WARNING", "CRITICAL")


class RequestProductionAlertUseCase:
    def __init__(
        self,
        authorization: MeatProcessingAuthorizationPolicy | None = None,
        notification_port: NotificationPort | None = None,
    ) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()
        self._notifications = notification_port or NullNotificationPort()

    def execute(
        self, connection, *, operation_id: str, alert_type: str, severity: str, message: str,
        branch_id: str, actor_user_id: str, context=None,
    ) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.ALERT_SEND)
        except MeatProcessingPermissionDeniedError as exc:
            return _fail(exc, operation_id)
        if severity not in _VALID_SEVERITIES:
            return MeatProcessingResult.fail(
                "Severidad de alerta inválida", "INVALID_SEVERITY", operation_id=operation_id)
        if context is not None:
            try:
                context.enforce_branch(branch_id)
            except MeatProcessingScopeError as exc:
                return _fail(exc, operation_id)
        try:
            with MeatProcessingUnitOfWork(connection) as uow:
                if uow.processed_events.was_processed(operation_id):
                    return MeatProcessingResult.ok(
                        "Alerta ya solicitada (idempotente)", operation_id=operation_id,
                        already_processed=True)
                notification_reference = self._notifications.send_alert(
                    operation_id=operation_id, alert_type=alert_type, severity=severity,
                    message=message, branch_id=branch_id)
                if notification_reference is None:
                    return MeatProcessingResult.fail(
                        "Notificaciones aún no confirma el envío",
                        "NOTIFICATION_INTEGRATION_PENDING", operation_id=operation_id)
                alert_id = new_uuid()
                uow.audit.record(
                    entity_type="ProductionAlert", entity_id=alert_id, action="REQUESTED",
                    user_id=actor_user_id, operation_id=operation_id, branch_id=branch_id,
                    reason=message,
                    after_json=json.dumps({
                        "alert_type": alert_type, "severity": severity,
                        "notification_reference": notification_reference}))
                payload = build_meat_processing_event(
                    MeatProcessingEvents.PROCESSING_ALERT_REQUESTED, operation_id=operation_id,
                    entity_id=alert_id, branch_id=branch_id, user_id=actor_user_id,
                    alert_type=alert_type, severity=severity, message=message,
                    notification_reference=notification_reference)
                uow.outbox.enqueue(
                    event_id=payload["event_id"],
                    event_name=MeatProcessingEvents.PROCESSING_ALERT_REQUESTED,
                    payload_json=json.dumps(payload), operation_id=operation_id)
                uow.processed_events.mark_processed(
                    operation_id, "PROCESSING_ALERT_REQUESTED", operation_id)
        except MeatProcessingError as exc:
            return _fail(exc, operation_id)
        return MeatProcessingResult.ok(
            "Alerta solicitada", entity_id=alert_id, operation_id=operation_id,
            notification_reference=notification_reference)
