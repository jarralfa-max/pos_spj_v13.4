"""Desktop notification channel — QSystemTrayIcon balloon messages."""
from __future__ import annotations

import logging
from typing import Any, Optional

from notifications.base import NotificationChannel, NotificationPayload

logger = logging.getLogger("spj.notifications.desktop")

_TRAY_ICON: Optional[Any] = None


def set_tray_icon(tray) -> None:
    """Register the app QSystemTrayIcon (called once during app init)."""
    global _TRAY_ICON
    _TRAY_ICON = tray


_PRIORITY_TO_ICON = {
    "low":    1,  # QSystemTrayIcon.Information
    "normal": 1,
    "high":   2,  # QSystemTrayIcon.Warning
    "urgent": 3,  # QSystemTrayIcon.Critical
}


class DesktopNotificationChannel(NotificationChannel):
    """Shows OS desktop notifications via QSystemTrayIcon."""

    def is_available(self) -> bool:
        return _TRAY_ICON is not None

    def send(self, payload: NotificationPayload) -> bool:
        if not self.is_available():
            return False
        msg_type = _PRIORITY_TO_ICON.get(payload.priority, 1)
        try:
            from PyQt5.QtCore import QTimer
            from PyQt5.QtWidgets import QSystemTrayIcon
            icon_map = {
                1: QSystemTrayIcon.Information,
                2: QSystemTrayIcon.Warning,
                3: QSystemTrayIcon.Critical,
            }
            icon = icon_map.get(msg_type, QSystemTrayIcon.Information)
            QTimer.singleShot(
                0,
                lambda: _TRAY_ICON.showMessage(payload.title, payload.body, icon, 4000),
            )
            return True
        except Exception as exc:
            logger.warning("DesktopChannel send failed: %s", exc)
            return False
