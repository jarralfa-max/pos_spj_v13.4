"""Audited, idempotent delivery of transfer alerts through channel gateways."""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from backend.domain.transfers.policies.transfer_notification_policy import (
    TransferNotificationChannel, TransferNotificationPolicy,
)
from backend.shared.ids import new_uuid


@dataclass(frozen=True, slots=True)
class TransferNotificationRecipient:
    user_id: str
    role_code: str
    in_app_address: str
    whatsapp_address: str | None = None


@dataclass(frozen=True, slots=True)
class TransferNotificationMessage:
    notification_id: str
    event_id: str
    transfer_id: str
    recipient_user_id: str
    channel: TransferNotificationChannel
    severity: str
    title: str
    body: str
    operation_id: str


class TransferRecipientQueryService(Protocol):
    def resolve(self, *, transfer_id: str, role_codes: tuple[str, ...],
                branch_ids: tuple[str, ...]) -> tuple[TransferNotificationRecipient, ...]: ...


class InAppTransferNotifier(Protocol):
    def send(self, message: TransferNotificationMessage) -> None: ...


class WhatsAppTransferNotifier(Protocol):
    def send(self, message: TransferNotificationMessage, destination: str) -> None: ...


class TransferNotificationDeliveryRepository(Protocol):
    def was_delivered(self, *, event_id: str, recipient_user_id: str,
                      channel: str) -> bool: ...
    def record_delivery(self, *, message: TransferNotificationMessage,
                        destination: str, delivered_at: str) -> None: ...


class TransferNotificationAuditSink(Protocol):
    def record(self, *, transfer_id: str, operation_id: str, action: str,
               recipient_user_id: str, channel: str, event_id: str) -> None: ...


class TransferNotificationHandler:
    def __init__(self, *, policy: TransferNotificationPolicy,
                 recipients: TransferRecipientQueryService,
                 deliveries: TransferNotificationDeliveryRepository,
                 in_app: InAppTransferNotifier,
                 whatsapp: WhatsAppTransferNotifier,
                 audit: TransferNotificationAuditSink) -> None:
        self._policy = policy
        self._recipients = recipients
        self._deliveries = deliveries
        self._in_app = in_app
        self._whatsapp = whatsapp
        self._audit = audit

    def handle(self, event: dict[str, object]) -> int:
        event_name = str(event.get("event_name", ""))
        rule = self._policy.rule_for(event_name)
        if rule is None:
            return 0
        event_id = self._required(event, "event_id")
        transfer_id = self._required(event, "entity_id")
        operation_id = self._required(event, "operation_id")
        branch_ids = tuple(str(value) for value in event.get("branch_ids", ()))
        recipients = self._recipients.resolve(
            transfer_id=transfer_id, role_codes=rule.recipient_roles,
            branch_ids=branch_ids)
        delivered = 0
        for recipient in recipients:
            for channel in self._policy.channels_for(rule):
                destination = self._destination(recipient, channel)
                if destination is None or self._deliveries.was_delivered(
                        event_id=event_id, recipient_user_id=recipient.user_id,
                        channel=channel.value):
                    continue
                message = TransferNotificationMessage(
                    notification_id=new_uuid(), event_id=event_id,
                    transfer_id=transfer_id, recipient_user_id=recipient.user_id,
                    channel=channel, severity=rule.severity.value,
                    title=str(event.get("title", event_name)),
                    body=str(event.get("message", event_name)), operation_id=operation_id)
                if channel is TransferNotificationChannel.IN_APP:
                    self._in_app.send(message)
                else:
                    self._whatsapp.send(message, destination)
                self._deliveries.record_delivery(
                    message=message, destination=destination,
                    delivered_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
                self._audit.record(
                    transfer_id=transfer_id, operation_id=operation_id,
                    action="TRANSFER_NOTIFICATION_SENT",
                    recipient_user_id=recipient.user_id, channel=channel.value,
                    event_id=event_id)
                delivered += 1
        return delivered

    @staticmethod
    def _required(event: dict[str, object], key: str) -> str:
        value = str(event.get(key, "")).strip()
        if not value:
            raise ValueError(f"Transfer notification event requires {key}")
        return value

    @staticmethod
    def _destination(recipient: TransferNotificationRecipient,
                     channel: TransferNotificationChannel) -> str | None:
        if channel is TransferNotificationChannel.IN_APP:
            return recipient.in_app_address
        return recipient.whatsapp_address
