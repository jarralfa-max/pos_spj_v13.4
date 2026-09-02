"""Canonical enums for the Notifications bounded context — SET-20. See
docs/refactor/settings_refactor_execution_plan.md. Generalizes the real,
live notification channels already in this codebase —
`backend/infrastructure/integrations/cash_notification_senders.py::
WhatsAppNotificationSender`/`EmailNotificationSender` (CASH-*) and
`loss_notification_senders.py::LossWhatsAppNotificationSender` (LOSS-19)
— into a typed vocabulary, adding SMS/PUSH as the two channel kinds the
master prompt's own notification taxonomy expects but no live sender
implements yet.
"""

from __future__ import annotations

from enum import Enum


class NotificationChannel(str, Enum):
    WHATSAPP = "WHATSAPP"
    SMS = "SMS"
    EMAIL = "EMAIL"
    PUSH = "PUSH"


# Channels whose recipient is a phone number validated as E.164 — same
# pattern `cash_notification_senders.py::WhatsAppNotificationSender`
# already enforces (`r"\+[1-9]\d{7,14}"`).
PHONE_ADDRESSED_CHANNELS = frozenset({NotificationChannel.WHATSAPP, NotificationChannel.SMS})
