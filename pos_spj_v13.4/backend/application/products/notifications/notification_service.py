"""ProductNotificationService — build, throttle, deliver and audit alerts (§35, §36).

Given an alert, the service resolves severity + channels (policy), suppresses a
repeat of the same (alert_type, entity, channel, recipient) inside a throttle
window, delivers via the gateway, records every attempt in
``product_notification_log`` (SENT / FAILED / THROTTLED) and dispatches the
canonical events (PRODUCT_NOTIFICATION_CREATED / PRODUCT_WHATSAPP_ALERT_SENT).
Never crashes the caller on a delivery failure.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.application.products.notifications.gateway import (
    NotificationDeliveryError,
)
from backend.application.products.notifications.notification_policy import (
    channels_for,
    severity_for,
)
from backend.domain.products.events import ProductEvents
from backend.domain.products.notification_enums import (
    NotificationChannel,
    ProductAlertType,
)
from backend.shared.ids import new_uuid


@dataclass(frozen=True)
class NotificationOutcome:
    sent: int
    throttled: int
    failed: int


class ProductNotificationService:
    def __init__(
        self,
        connection,
        *,
        gateway=None,
        event_dispatcher=None,
        throttle_seconds: int = 3600,
    ) -> None:
        self._conn = connection
        self._gateway = gateway
        self._dispatch = event_dispatcher
        self._throttle_seconds = int(throttle_seconds)

    def notify(
        self,
        alert_type: ProductAlertType,
        *,
        entity_id: str,
        message: str,
        recipients: list[str],
        operation_id: str | None = None,
        whatsapp_enabled: bool = True,
        context: dict | None = None,
    ) -> NotificationOutcome:
        severity = severity_for(alert_type)
        channels = channels_for(alert_type, whatsapp_enabled=whatsapp_enabled)
        ctx = dict(context or {})
        sent = throttled = failed = 0

        for channel in channels:
            for recipient in recipients:
                if self._is_throttled(alert_type, entity_id, channel, recipient):
                    self._log(alert_type, severity, channel, recipient, entity_id,
                              message, "THROTTLED", operation_id)
                    throttled += 1
                    continue
                status = "SENT"
                if self._gateway is not None:
                    try:
                        self._gateway.send(channel=channel.value, recipient_ref=recipient,
                                           message=message, context=ctx)
                    except NotificationDeliveryError:
                        status = "FAILED"
                self._log(alert_type, severity, channel, recipient, entity_id,
                          message, status, operation_id)
                if status == "SENT":
                    sent += 1
                    self._emit(channel, alert_type, entity_id, severity, operation_id)
                else:
                    failed += 1
        return NotificationOutcome(sent=sent, throttled=throttled, failed=failed)

    # ── internals ─────────────────────────────────────────────────────────
    def _is_throttled(self, alert_type, entity_id, channel, recipient) -> bool:
        row = self._conn.execute(
            f"""SELECT 1 FROM product_notification_log
                WHERE alert_type=? AND entity_id=? AND channel=? AND recipient_ref=?
                  AND status='SENT'
                  AND created_at >= datetime('now', '-{self._throttle_seconds} seconds')
                LIMIT 1""",
            (alert_type.value, entity_id, channel.value, recipient)).fetchone()
        return row is not None

    def _log(self, alert_type, severity, channel, recipient, entity_id, message,
             status, operation_id) -> None:
        self._conn.execute(
            """INSERT INTO product_notification_log
               (id, alert_type, severity, channel, recipient_ref, entity_id,
                message, status, operation_id)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (new_uuid(), alert_type.value, severity.value, channel.value, recipient,
             entity_id, message, status, operation_id))

    def _emit(self, channel, alert_type, entity_id, severity, operation_id) -> None:
        if self._dispatch is None:
            return
        payload = {"alert_type": alert_type.value, "entity_id": entity_id,
                   "severity": severity.value, "operation_id": operation_id}
        self._dispatch(ProductEvents.PRODUCT_NOTIFICATION_CREATED, payload)
        if channel is NotificationChannel.WHATSAPP:
            self._dispatch(ProductEvents.PRODUCT_WHATSAPP_ALERT_SENT, payload)
