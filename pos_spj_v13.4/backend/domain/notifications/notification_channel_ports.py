"""NotificationChannelPort — SET-20 "Channels". Distinct from
`webhook_verification_ports.py` (Integrations, SET-19, inbound) and
`gateway_ports.py` (Customer Display, SET-17, screen push): this is the
outbound send contract. **No real implementation here, on purpose** —
real senders already exist per-module
(`backend/infrastructure/integrations/cash_notification_senders.py::
WhatsAppNotificationSender`/`EmailNotificationSender`,
`loss_notification_senders.py::LossWhatsAppNotificationSender`), each
wrapping a real provider client (Meta's API, an SMTP client) this
bounded context has no business importing or duplicating. A future
consolidation would adapt those existing senders to this Protocol, not
the other way around.
"""

from __future__ import annotations

from typing import Protocol

from backend.domain.notifications.value_objects.notification_message import NotificationMessage


class NotificationChannelPort(Protocol):
    def send(self, message: NotificationMessage) -> str:
        """Send `message` and return a provider delivery id. Must raise
        rather than return a placeholder id on delivery failure — the
        caller (a future use case) decides how to handle that failure."""
        ...
