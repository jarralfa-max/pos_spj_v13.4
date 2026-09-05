"""AlertNotificationService (§51-55, BI-21) — resolves candidate recipients
for an alert, filters them through their own subscription preferences
(opt-in, quiet hours, minimum severity), groups by channel, and dispatches.

Never imports WhatsApp/NotificationDispatcher concretely — only the two
ports (`AlertRecipientResolverPort`, `AlertDispatchPort`) an infrastructure
adapter implements.
"""

from __future__ import annotations

from datetime import datetime

from backend.domain.analytical_alerting.integration_ports import (
    AlertDispatchPort,
    AlertRecipientResolverPort,
)
from backend.domain.analytical_alerting.services.notification_gating import should_notify
from backend.domain.analytical_alerting.value_objects.alert import AnalyticalAlert
from backend.domain.analytical_alerting.value_objects.notification_subscription import (
    AnalyticalNotificationSubscription,
)
from backend.domain.notifications.enums import NotificationChannel


class AlertNotificationService:
    def __init__(
        self,
        recipient_resolver: AlertRecipientResolverPort,
        dispatch_port: AlertDispatchPort,
    ) -> None:
        self._recipient_resolver = recipient_resolver
        self._dispatch_port = dispatch_port

    def notify(
        self,
        alert: AnalyticalAlert,
        subscriptions: tuple[AnalyticalNotificationSubscription, ...],
        now: datetime,
    ) -> dict[NotificationChannel, tuple[str, ...]]:
        """Returns the user_ids actually notified, grouped by channel — for
        callers that want to record/audit what happened without re-deriving
        it from the dispatch port's side effects."""
        candidates = self._recipient_resolver.resolve(alert.alert_type, alert.branch_id)
        subscriptions_by_user = {s.user_id: s for s in subscriptions}

        grouped: dict[NotificationChannel, list] = {}
        for recipient in candidates:
            subscription = subscriptions_by_user.get(recipient.user_id)
            if subscription is None:
                continue
            if not should_notify(subscription, alert, now.time()):
                continue
            grouped.setdefault(subscription.channel, []).append(recipient)

        for channel, recipients in grouped.items():
            self._dispatch_port.dispatch(alert, tuple(recipients), channel)

        return {
            channel: tuple(r.user_id for r in recipients)
            for channel, recipients in grouped.items()
        }
