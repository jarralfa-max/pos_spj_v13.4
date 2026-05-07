"""Notifications package — multi-channel, event-driven, decoupled from UI.

Public API:
    from notifications import DeliveryNotificationService, NotificationPayload
    from notifications.service import build_default_service

All channels are optional/lazy-loaded; a missing dependency silently disables
that channel without raising.
"""
from __future__ import annotations

from notifications.base import NotificationChannel, NotificationPayload
from notifications.service import DeliveryNotificationService

__all__ = [
    "NotificationChannel",
    "NotificationPayload",
    "DeliveryNotificationService",
]
