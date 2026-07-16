"""Canonical inline feedback components."""

from __future__ import annotations

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QLabel


class InlineFeedback(QLabel):
    """Contextual feedback label controlled by semantic variant properties."""

    def __init__(self, text: str = "", parent=None, *, variant: str = "info") -> None:
        super().__init__(text, parent)
        self.setObjectName("inlineFeedback")
        self.setProperty("component", "inlineFeedback")
        self.setProperty("variant", variant)
        self.setWordWrap(True)
        self.setAccessibleName(text or "Feedback")


class StatusMessage(InlineFeedback):
    """Persistent status message for views and forms."""

    def __init__(self, text: str = "", parent=None, *, variant: str = "info") -> None:
        super().__init__(text, parent, variant=variant)
        self.setObjectName("statusMessage")


class Toast(StatusMessage):
    """Transient toast message with semantic variant metadata."""

    def __init__(self, text: str = "", parent=None, *, variant: str = "info", timeout_ms: int = 3500) -> None:
        super().__init__(text, parent, variant=variant)
        self.setObjectName("toast")
        self.setProperty("component", "toast")
        self._timeout_ms = timeout_ms
        self.setVisible(bool(text))

    def show_message(self, text: str, *, variant: str | None = None) -> None:
        self.setText(text)
        self.setAccessibleName(text)
        if variant is not None:
            self.setProperty("variant", variant)
        self.setVisible(True)
        QTimer.singleShot(self._timeout_ms, self.hide)
