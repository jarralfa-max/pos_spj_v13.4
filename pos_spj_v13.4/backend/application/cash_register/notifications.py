"""Policy-driven, idempotent CASH-20 notification routing and delivery."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.permissions import CashPermissions
from backend.infrastructure.db.repositories.cash_register.unit_of_work import CashRegisterUnitOfWork
from backend.shared.ids import new_uuid, validate_uuidv7


def _now() -> datetime: return datetime.now(timezone.utc)
def _iso(value: datetime) -> str: return value.isoformat(timespec="seconds")


@dataclass(frozen=True, slots=True)
class CashNotificationMessage:
    job_id: str
    recipient: str
    severity: str
    title: str
    body: str


class CashNotificationSender(Protocol):
    def send(self, message: CashNotificationMessage) -> str: ...


@dataclass(frozen=True, slots=True)
class NotificationDispatchResult:
    prepared: int = 0
    delivered: int = 0
    retries: int = 0
    skipped: int = 0


class PrepareCashNotificationsUseCase:
    """Resolve the effective policy and materialize one job per recipient."""

    def execute(self, connection, *, event_id: str) -> NotificationDispatchResult:
        validate_uuidv7(event_id)
        with CashRegisterUnitOfWork(connection) as uow:
            event = uow.notifications.get_event(event_id)
            if event is None:
                raise LookupError("Cash event not found")
            policy = uow.notifications.resolve_policy(
                event_name=event["event_name"], branch_id=event["branch_id"],
                occurred_at=event["occurred_at"],
            )
            if policy is None:
                return NotificationDispatchResult()
            payload = json.loads(event["payload_json"])
            title = f"Caja · {event['event_name']}"
            body = json.dumps(payload, ensure_ascii=False, sort_keys=True)
            prepared = 0
            for channel in policy["channels"]:
                for recipient in uow.notifications.recipients(
                        rule_id=policy["id"], channel=channel):
                    prepared += int(uow.notifications.add_job(
                        source_event_id=event_id, rule_id=policy["id"],
                        channel=channel, recipient=recipient,
                        severity=policy["severity"], title=title, body=body,
                        created_at=_iso(_now()),
                    ))
        return NotificationDispatchResult(prepared=prepared)


class DispatchCashNotificationsUseCase:
    def __init__(self, *, whatsapp: CashNotificationSender | None = None,
                 email: CashNotificationSender | None = None,
                 max_attempts: int = 5, batch_size: int = 50) -> None:
        if max_attempts < 1 or not 1 <= batch_size <= 500:
            raise ValueError("Invalid notification dispatch limits")
        self._senders = {"WHATSAPP": whatsapp, "EMAIL": email}
        self._max_attempts, self._batch_size = max_attempts, batch_size

    def execute(self, connection, *, now: datetime | None = None) -> NotificationDispatchResult:
        instant = now or _now(); timestamp = _iso(instant)
        with CashRegisterUnitOfWork(connection) as uow:
            jobs = uow.notifications.ready(now=timestamp, limit=self._batch_size)
        delivered = retries = skipped = 0
        for job in jobs:
            with CashRegisterUnitOfWork(connection) as uow:
                if not uow.notifications.claim(job["id"]):
                    continue
            message = CashNotificationMessage(
                job["id"], job["recipient"], job["severity"],
                job["title"], job["body"],
            )
            status, reference, error, next_attempt = "DELIVERED", "", "", None
            if job["channel"] != "IN_APP":
                sender = self._senders[job["channel"]]
                if sender is None and job["channel"] == "EMAIL":
                    status, error = "SKIPPED", "EMAIL_DISABLED"
                elif sender is None:
                    status, error = "RETRY", "WHATSAPP_NOT_CONFIGURED"
                else:
                    try:
                        reference = sender.send(message)
                    except Exception:
                        status, error = "RETRY", "PROVIDER_UNAVAILABLE"
            attempt_no = int(job["attempt_count"]) + 1
            if status == "RETRY":
                if attempt_no >= self._max_attempts:
                    status = "DEAD_LETTER"
                else:
                    next_attempt = _iso(instant + timedelta(
                        seconds=min(900, 2 ** min(attempt_no, 10))))
            with CashRegisterUnitOfWork(connection) as uow:
                if job["channel"] == "IN_APP" and status == "DELIVERED":
                    uow.notifications.create_in_app_alert(job=job, created_at=timestamp)
                uow.notifications.finish(
                    job=job, status=status, attempted_at=timestamp,
                    provider_reference=reference, error_code=error,
                    next_attempt_at=next_attempt,
                )
                uow.audit.record(
                    audit_id=new_uuid(),
                    action=f"CASH_NOTIFICATION_{status}",
                    actor_user_id=job["user_id"], entity_id=job["id"],
                    branch_id=job["branch_id"], operation_id=job["operation_id"],
                    reason=error, occurred_at=timestamp,
                )
            delivered += int(status == "DELIVERED")
            retries += int(status in {"RETRY", "DEAD_LETTER"})
            skipped += int(status == "SKIPPED")
        return NotificationDispatchResult(delivered=delivered, retries=retries, skipped=skipped)


class CashInAppAlertQueryService:
    def __init__(self, authorization: CashAuthorizationPolicy) -> None:
        self._authorization = authorization

    def unread(self, connection, *, user_id: str, branch_id: str) -> list[dict]:
        self._authorization.require(user_id=user_id, permission_code=CashPermissions.NOTIFICATIONS_VIEW,
                                    branch_id=branch_id)
        with CashRegisterUnitOfWork(connection) as uow:
            return uow.notifications.unread(user_id=user_id)

    def dashboard(self, connection, *, user_id: str, branch_id: str) -> dict[str, int]:
        self._authorization.require(user_id=user_id, permission_code=CashPermissions.NOTIFICATIONS_VIEW,
                                    branch_id=branch_id)
        with CashRegisterUnitOfWork(connection) as uow:
            counts = uow.notifications.job_counts(branch_id=branch_id)
            return {
                "unread": uow.notifications.unread_count(user_id=user_id),
                "pending": counts.get("PENDING", 0) + counts.get("RETRY", 0),
                "delivered": counts.get("DELIVERED", 0),
                "dead_letter": counts.get("DEAD_LETTER", 0),
                "skipped": counts.get("SKIPPED", 0),
            }

    def recent_jobs(self, connection, *, user_id: str, branch_id: str,
                    limit: int = 100) -> list[dict]:
        self._authorization.require(user_id=user_id, permission_code=CashPermissions.NOTIFICATIONS_VIEW,
                                    branch_id=branch_id)
        with CashRegisterUnitOfWork(connection) as uow:
            return uow.notifications.recent_jobs(branch_id=branch_id, limit=limit)
