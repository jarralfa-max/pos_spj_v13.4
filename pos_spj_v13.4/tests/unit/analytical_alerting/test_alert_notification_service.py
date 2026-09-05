from datetime import datetime, timezone

from backend.application.analytical_alerting.services.alert_notification_service import (
    AlertNotificationService,
)
from backend.domain.analytical_alerting.enums import AlertSeverity, AlertStatus, AlertType
from backend.domain.analytical_alerting.integration_ports import AlertRecipient
from backend.domain.analytical_alerting.value_objects.alert import AnalyticalAlert
from backend.domain.analytical_alerting.value_objects.notification_subscription import (
    ALL_BRANCHES,
    AnalyticalNotificationSubscription,
)
from backend.domain.notifications.enums import NotificationChannel
from backend.shared.ids import new_uuid

_NOW = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)


class _FakeResolver:
    def __init__(self, recipients):
        self._recipients = recipients

    def resolve(self, alert_type, branch_id):
        return tuple(self._recipients)


class _FakeDispatchPort:
    def __init__(self):
        self.dispatched = []

    def dispatch(self, alert, recipients, channel):
        self.dispatched.append((channel, recipients))


def _alert() -> AnalyticalAlert:
    return AnalyticalAlert(
        id=new_uuid(), rule_id=new_uuid(), alert_type=AlertType.STOCKOUT_RISK,
        severity=AlertSeverity.HIGH, title="t", message="m", branch_id="b1", target_id="p1",
        evidence={"x": "1"}, fingerprint="STOCKOUT_RISK:b1:p1", status=AlertStatus.OPEN,
        created_at=_NOW,
    )


def _subscription(user_id, **overrides) -> AnalyticalNotificationSubscription:
    fields = dict(
        id=new_uuid(), user_id=user_id, alert_type=AlertType.STOCKOUT_RISK,
        minimum_severity=AlertSeverity.MEDIUM, channel=NotificationChannel.IN_APP,
        branch_scope=ALL_BRANCHES,
    )
    fields.update(overrides)
    return AnalyticalNotificationSubscription(**fields)


def test_notifies_only_subscribed_candidates():
    recipients = (
        AlertRecipient(user_id="user1", display_name="Ana"),
        AlertRecipient(user_id="user2", display_name="Beto"),  # no subscription
    )
    resolver = _FakeResolver(recipients)
    dispatcher = _FakeDispatchPort()
    service = AlertNotificationService(resolver, dispatcher)

    result = service.notify(_alert(), (_subscription("user1"),), _NOW)

    assert result == {NotificationChannel.IN_APP: ("user1",)}
    assert len(dispatcher.dispatched) == 1
    channel, dispatched_recipients = dispatcher.dispatched[0]
    assert channel == NotificationChannel.IN_APP
    assert dispatched_recipients[0].user_id == "user1"


def test_groups_recipients_by_channel():
    recipients = (
        AlertRecipient(user_id="user1", display_name="Ana"),
        AlertRecipient(user_id="user2", display_name="Beto", phone_e164="+525512345678"),
    )
    resolver = _FakeResolver(recipients)
    dispatcher = _FakeDispatchPort()
    service = AlertNotificationService(resolver, dispatcher)

    subscriptions = (
        _subscription("user1", channel=NotificationChannel.IN_APP),
        _subscription("user2", channel=NotificationChannel.WHATSAPP),
    )
    result = service.notify(_alert(), subscriptions, _NOW)

    assert set(result.keys()) == {NotificationChannel.IN_APP, NotificationChannel.WHATSAPP}
    assert len(dispatcher.dispatched) == 2


def test_no_dispatch_when_no_candidate_is_subscribed():
    resolver = _FakeResolver((AlertRecipient(user_id="user1", display_name="Ana"),))
    dispatcher = _FakeDispatchPort()
    service = AlertNotificationService(resolver, dispatcher)

    result = service.notify(_alert(), (), _NOW)

    assert result == {}
    assert dispatcher.dispatched == []


def test_gating_excludes_subscription_below_minimum_severity():
    resolver = _FakeResolver((AlertRecipient(user_id="user1", display_name="Ana"),))
    dispatcher = _FakeDispatchPort()
    service = AlertNotificationService(resolver, dispatcher)

    subscriptions = (_subscription("user1", minimum_severity=AlertSeverity.CRITICAL),)
    result = service.notify(_alert(), subscriptions, _NOW)  # alert severity is HIGH

    assert result == {}
    assert dispatcher.dispatched == []
