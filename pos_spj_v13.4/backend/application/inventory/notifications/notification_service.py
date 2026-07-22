"""InventoryNotificationService + SetNotificationRuleUseCase (§55, INV-23).

``notify(event)`` is the alert fan-out: derive the event's severity, match the
active routing rules in scope, and for each — gate by minimum severity, dedupe by
the event's id (idempotent: the same event never notifies twice), throttle
repeats within the rule's window, then deliver through the gateway. Every outcome
(SENT / FAILED / THROTTLED / SUPPRESSED) is written to the audit log and, on a
delivery, an INVENTORY_NOTIFICATION_CREATED event (plus INVENTORY_WHATSAPP_ALERT_SENT
for WhatsApp) is enqueued. All in one atomic UnitOfWork.

``SetNotificationRuleUseCase`` manages the routing rules behind the granular
permission (WhatsApp rules require the WhatsApp-alerts permission).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from backend.application.inventory.authorization import InventoryAuthorizationPolicy
from backend.application.inventory.notifications.gateway import (
    InMemoryNotificationGateway,
)
from backend.application.inventory.permissions import InventoryPermissions
from backend.application.inventory.result import InventoryResult
from backend.domain.inventory.entities.notification_rule import NotificationRule
from backend.domain.inventory.enums import (
    ALERT_EVENT_SEVERITY,
    NotificationChannel,
    NotificationRecipientType,
    NotificationSeverity,
    NotificationStatus,
    severity_rank,
)
from backend.domain.inventory.events import InventoryEvents, build_event_payload
from backend.domain.inventory.exceptions import (
    InventoryDomainError,
    InventoryPermissionDeniedError,
)
from backend.infrastructure.db.repositories.inventory.unit_of_work import (
    InventoryUnitOfWork,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _severity_of(event: dict) -> NotificationSeverity:
    raw = event.get("severity")
    if raw:
        return NotificationSeverity(raw)
    return ALERT_EVENT_SEVERITY.get(str(event.get("event_name") or ""),
                                    NotificationSeverity.INFO)


def _scope_matches(rule: dict, event: dict) -> bool:
    scope_type = rule["scope_type"]
    if scope_type == "GLOBAL":
        return True
    if scope_type == "BRANCH":
        return rule["scope_id"] == str(event.get("branch_id") or "")
    if scope_type == "WAREHOUSE":
        return rule["scope_id"] == str(event.get("warehouse_id") or "")
    return False


class InventoryNotificationService:
    def __init__(self, gateway=None) -> None:
        self._gateway = gateway or InMemoryNotificationGateway()

    def notify(self, connection, event: dict, *, now: str | None = None) -> InventoryResult:
        event_id = str(event.get("event_id") or "").strip()
        event_name = str(event.get("event_name") or "").strip()
        if not event_id or not event_name:
            return InventoryResult.fail("Evento sin event_id/event_name",
                                        "INVALID_EVENT")
        now = now or _now()
        severity = _severity_of(event)
        stats = {"sent": 0, "throttled": 0, "suppressed": 0, "failed": 0, "deduped": 0}

        with InventoryUnitOfWork(connection) as uow:
            for rule in uow.notification_rules.list_for_event(event_name):
                if not _scope_matches(rule, event):
                    continue
                if severity_rank(severity) < severity_rank(
                        NotificationSeverity(rule["min_severity"])):
                    stats["suppressed"] += 1
                    continue
                dedupe_key = f"{event_id}:{rule['channel']}:{rule['recipient_ref']}"
                if uow.notification_log.exists(dedupe_key):
                    stats["deduped"] += 1
                    continue
                if self._throttled(uow, rule, now):
                    self._log(uow, event, rule, severity, NotificationStatus.THROTTLED,
                              dedupe_key, "", now)
                    stats["throttled"] += 1
                    continue
                message = self._build_message(event, severity)
                status = self._deliver(rule, message, event)
                self._log(uow, event, rule, severity, status, dedupe_key, message, now)
                if status is NotificationStatus.SENT:
                    stats["sent"] += 1
                    self._emit(uow, event, rule, severity)
                else:
                    stats["failed"] += 1

        return InventoryResult.ok("Notificaciones procesadas", **stats)

    # ── internals ────────────────────────────────────────────────────────────
    def _throttled(self, uow, rule: dict, now: str) -> bool:
        window = rule["throttle_seconds"]
        if not window:
            return False
        last = uow.notification_log.last_sent_at(
            event_name=rule["event_name"], channel=rule["channel"],
            recipient_ref=rule["recipient_ref"])
        if not last:
            return False
        elapsed = (datetime.fromisoformat(now) - datetime.fromisoformat(last)).total_seconds()
        return elapsed < window

    def _deliver(self, rule: dict, message: str, event: dict) -> NotificationStatus:
        try:
            self._gateway.send(channel=rule["channel"],
                               recipient_ref=rule["recipient_ref"], message=message,
                               context=event)
        except Exception:  # noqa: BLE001 — any delivery failure is logged, never raised
            return NotificationStatus.FAILED
        return NotificationStatus.SENT

    @staticmethod
    def _build_message(event: dict, severity: NotificationSeverity) -> str:
        parts = [f"[{severity.value}] {event.get('event_name')}"]
        if event.get("product_id"):
            parts.append(f"producto={event['product_id']}")
        if event.get("warehouse_id"):
            parts.append(f"almacén={event['warehouse_id']}")
        if event.get("message"):
            parts.append(str(event["message"]))
        return " ".join(parts)

    @staticmethod
    def _log(uow, event, rule, severity, status, dedupe_key, message, created_at) -> None:
        uow.notification_log.record(
            event_id=str(event.get("event_id")), event_name=rule["event_name"],
            rule_id=rule["id"], channel=rule["channel"],
            recipient_ref=rule["recipient_ref"], severity=severity.value,
            status=status.value, dedupe_key=dedupe_key, message=message,
            branch_id=event.get("branch_id"), warehouse_id=event.get("warehouse_id"),
            product_id=event.get("product_id"), created_at=created_at)

    @staticmethod
    def _emit(uow, event, rule, severity) -> None:
        payload = build_event_payload(
            InventoryEvents.INVENTORY_NOTIFICATION_CREATED,
            operation_id=str(event.get("event_id")), entity_id=str(event.get("event_id")),
            product_id=event.get("product_id"), branch_id=event.get("branch_id"),
            warehouse_id=event.get("warehouse_id"), channel=rule["channel"],
            recipient_ref=rule["recipient_ref"], severity=severity.value,
            source_event=rule["event_name"])
        uow.outbox.enqueue(event_id=payload["event_id"],
                           event_name=InventoryEvents.INVENTORY_NOTIFICATION_CREATED,
                           payload_json=json.dumps(payload),
                           operation_id=payload["operation_id"])
        if rule["channel"] == NotificationChannel.WHATSAPP.value:
            wa = build_event_payload(
                InventoryEvents.INVENTORY_WHATSAPP_ALERT_SENT,
                operation_id=str(event.get("event_id")),
                entity_id=str(event.get("event_id")), recipient_ref=rule["recipient_ref"],
                severity=severity.value, source_event=rule["event_name"])
            uow.outbox.enqueue(event_id=wa["event_id"],
                               event_name=InventoryEvents.INVENTORY_WHATSAPP_ALERT_SENT,
                               payload_json=json.dumps(wa),
                               operation_id=wa["operation_id"])


class SetNotificationRuleUseCase:
    def __init__(self, authorization: InventoryAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or InventoryAuthorizationPolicy()

    def execute(self, connection, *, event_name: str, channel: NotificationChannel,
                recipient_type: NotificationRecipientType, recipient_ref: str,
                actor_user_id: str, scope_type: str = "GLOBAL", scope_id: str = "",
                min_severity: NotificationSeverity = NotificationSeverity.INFO,
                throttle_seconds: int = 0, active: bool = True) -> InventoryResult:
        permission = (InventoryPermissions.WHATSAPP_ALERTS_MANAGE
                      if channel is NotificationChannel.WHATSAPP
                      else InventoryPermissions.NOTIFICATIONS_MANAGE)
        try:
            self._auth.require(actor_user_id, permission)
        except InventoryPermissionDeniedError as exc:
            return InventoryResult.fail(str(exc), "PERMISSION_DENIED")
        try:
            rule = NotificationRule.create(
                event_name=event_name, channel=channel, recipient_type=recipient_type,
                recipient_ref=recipient_ref, scope_type=scope_type, scope_id=scope_id,
                min_severity=min_severity, throttle_seconds=throttle_seconds, active=active)
            with InventoryUnitOfWork(connection) as uow:
                uow.notification_rules.upsert(rule)
                uow.audit.record(entity_type="NOTIFICATION_RULE", entity_id=rule.id,
                                 action="UPSERT", user_id=actor_user_id)
        except InventoryDomainError as exc:
            return InventoryResult.fail(str(exc), "INVENTORY_RULE_VIOLATION")
        return InventoryResult.ok("Regla de notificación guardada", entity_id=rule.id)
