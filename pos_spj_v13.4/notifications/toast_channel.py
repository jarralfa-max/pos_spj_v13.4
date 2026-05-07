"""Toast notification channel — dispatches to the Qt main thread safely.

Uses QTimer.singleShot(0, ...) so it's safe to call from any thread as long
as a QApplication event loop is running.  Falls back silently if no GUI exists.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from notifications.base import NotificationChannel, NotificationPayload

logger = logging.getLogger("spj.notifications.toast")

# Optional: callers can register a custom toast function via set_toast_fn()
# Signature: fn(parent_widget, title: str, body: str, level: str) -> None
# level: "info" | "success" | "warning" | "error"
_TOAST_FN: Optional[Callable] = None
_PARENT_WIDGET: Optional[Any] = None


def set_toast_fn(fn: Callable, parent=None) -> None:
    """Register the app-level toast function (called once during app init)."""
    global _TOAST_FN, _PARENT_WIDGET
    _TOAST_FN = fn
    _PARENT_WIDGET = parent


_PRIORITY_TO_LEVEL = {
    "low":    "info",
    "normal": "info",
    "high":   "warning",
    "urgent": "error",
}


class ToastNotificationChannel(NotificationChannel):
    """Shows an in-app toast via the registered toast function.

    Delegates to the Toast widget in modulos/ui_components but stays decoupled
    via the registered callable.  Thread-safe via QTimer.singleShot.
    """

    def is_available(self) -> bool:
        return _TOAST_FN is not None

    def send(self, payload: NotificationPayload) -> bool:
        if not self.is_available():
            return False
        level = _PRIORITY_TO_LEVEL.get(payload.priority, "info")
        try:
            self._dispatch_to_main(payload.title, payload.body, level)
            return True
        except Exception as exc:
            logger.warning("ToastChannel send failed: %s", exc)
            return False

    def _dispatch_to_main(self, title: str, body: str, level: str) -> None:
        try:
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(0, lambda: self._show(title, body, level))
        except ImportError:
            self._show(title, body, level)

    def _show(self, title: str, body: str, level: str) -> None:
        if _TOAST_FN is None:
            return
        try:
            _TOAST_FN(_PARENT_WIDGET, title, body, level)
        except Exception as exc:
            logger.debug("ToastChannel _show: %s", exc)
