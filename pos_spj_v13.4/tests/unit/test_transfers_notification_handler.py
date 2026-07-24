from backend.application.transfers.notification_handlers import (
    TransferNotificationHandler, TransferNotificationRecipient,
)
from backend.domain.transfers.policies.transfer_notification_policy import (
    TransferAlertSeverity, TransferNotificationPolicy, TransferNotificationRule,
)


class Recipients:
    def resolve(self, **values):
        assert values["role_codes"] == ("DESTINATION_MANAGER", "QUALITY")
        return (
            TransferNotificationRecipient("user-1", "QUALITY", "user-1", "+521111"),
            TransferNotificationRecipient("user-2", "DESTINATION_MANAGER", "user-2"),
        )


class Notifier:
    def __init__(self): self.sent = []
    def send(self, message, *destination): self.sent.append((message, destination))


class Deliveries:
    def __init__(self): self.keys, self.records = set(), []
    def was_delivered(self, **key):
        return (key["event_id"], key["recipient_user_id"], key["channel"]) in self.keys
    def record_delivery(self, **values):
        message = values["message"]
        self.keys.add((message.event_id, message.recipient_user_id, message.channel.value))
        self.records.append(values)


class Audit:
    def __init__(self): self.records = []
    def record(self, **values): self.records.append(values)


def _policy(severity=TransferAlertSeverity.CRITICAL, whatsapp=True):
    return TransferNotificationPolicy((TransferNotificationRule(
        "TRANSFER_CRITICAL_ALERT_CREATED", severity,
        ("DESTINATION_MANAGER", "QUALITY"), whatsapp),))


def test_critical_alert_sends_in_app_and_configured_whatsapp_idempotently():
    in_app, whatsapp, deliveries, audit = Notifier(), Notifier(), Deliveries(), Audit()
    handler = TransferNotificationHandler(
        policy=_policy(), recipients=Recipients(), deliveries=deliveries,
        in_app=in_app, whatsapp=whatsapp, audit=audit)
    event = {"event_name": "TRANSFER_CRITICAL_ALERT_CREATED", "event_id": "event-1",
             "entity_id": "transfer-1", "operation_id": "operation-1",
             "branch_ids": ("origin", "destination"), "title": "Cadena de frío",
             "message": "Temperatura fuera de rango"}

    assert handler.handle(event) == 3
    assert handler.handle(event) == 0
    assert len(in_app.sent) == 2
    assert len(whatsapp.sent) == 1
    assert whatsapp.sent[0][1] == ("+521111",)
    assert len(deliveries.records) == len(audit.records) == 3
    assert {record["channel"] for record in audit.records} == {"IN_APP", "WHATSAPP"}


def test_whatsapp_requires_policy_and_high_severity_and_unknown_events_are_ignored():
    in_app, whatsapp = Notifier(), Notifier()
    handler = TransferNotificationHandler(
        policy=_policy(TransferAlertSeverity.WARNING, whatsapp=True),
        recipients=Recipients(), deliveries=Deliveries(), in_app=in_app,
        whatsapp=whatsapp, audit=Audit())
    event = {"event_name": "TRANSFER_CRITICAL_ALERT_CREATED", "event_id": "event-2",
             "entity_id": "transfer-1", "operation_id": "operation-2"}
    assert handler.handle(event) == 2
    assert len(in_app.sent) == 2 and whatsapp.sent == []
    assert handler.handle({"event_name": "TRANSFER_RECEIVED"}) == 0


def test_policy_rejects_duplicate_event_configuration():
    rule = TransferNotificationRule("EVENT", TransferAlertSeverity.INFO, ("AUDITOR",))
    try:
        TransferNotificationPolicy((rule, rule))
    except ValueError as error:
        assert "one notification rule" in str(error)
    else:
        raise AssertionError("duplicate notification policy must be rejected")
