r"""NotificationMessage — SET-20 "Channels": the ready-to-send payload a
`NotificationChannelPort` implementation delivers. Generalizes
`backend.application.cash_register.notifications.CashNotificationMessage`
(title/body/recipient/job_id) into the Notifications bounded context —
not imported (application-layer DTO, wrong dependency direction) — for
any module to build, not only Cash Register.

Recipient validation mirrors
`backend/infrastructure/integrations/cash_notification_senders.py`'s
real checks exactly: E.164 for phone-addressed channels
(`WhatsAppNotificationSender`'s `r"\+[1-9]\d{7,14}"`), `"@"` presence for
EMAIL (`EmailNotificationSender`'s check).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from backend.domain.notifications.enums import PHONE_ADDRESSED_CHANNELS, NotificationChannel
from backend.domain.notifications.exceptions import NotificationsInvalidValueError

_E164_PATTERN = re.compile(r"\+[1-9]\d{7,14}")


@dataclass(frozen=True, slots=True)
class NotificationMessage:
    channel: NotificationChannel
    recipient: str
    body: str
    title: str = ""
    operation_id: str = ""

    @classmethod
    def create(
        cls, *, channel: NotificationChannel, recipient: str, body: str, title: str = "",
        operation_id: str = "",
    ) -> "NotificationMessage":
        if not body.strip():
            raise NotificationsInvalidValueError("body es obligatorio")
        cls._assert_valid_recipient(channel, recipient)
        return cls(
            channel=channel, recipient=recipient.strip(), body=body.strip(), title=title.strip(),
            operation_id=operation_id,
        )

    @staticmethod
    def _assert_valid_recipient(channel: NotificationChannel, recipient: str) -> None:
        if channel in PHONE_ADDRESSED_CHANNELS:
            if not _E164_PATTERN.fullmatch(recipient.strip()):
                raise NotificationsInvalidValueError(
                    f"recipient debe ser un teléfono E.164 para {channel.value}, recibido {recipient!r}"
                )
        elif channel is NotificationChannel.EMAIL:
            if "@" not in recipient:
                raise NotificationsInvalidValueError(f"recipient inválido para EMAIL: {recipient!r}")
        elif not recipient.strip():
            raise NotificationsInvalidValueError("recipient es obligatorio")
