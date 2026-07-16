"""Canonical inline feedback components."""

from __future__ import annotations

from PyQt5.QtWidgets import QLabel


class InlineFeedback(QLabel):
    """Contextual feedback label controlled by semantic variant properties."""

    def __init__(self, text: str = "", parent=None, *, variant: str = "info") -> None:
        super().__init__(text, parent)
        self.setObjectName("inlineFeedback")
        self.setProperty("component", "inlineFeedback")
        self.setProperty("variant", variant)
        self.setWordWrap(True)


class StatusMessage(InlineFeedback):
    """Persistent status message for views and forms."""

    def __init__(self, text: str = "", parent=None, *, variant: str = "info") -> None:
        super().__init__(text, parent, variant=variant)
        self.setObjectName("statusMessage")
