"""Canonical stale/freshness state component."""

from __future__ import annotations

from frontend.desktop.components.empty_state import EmptyState


class StaleState(EmptyState):
    """State shown when data is available but not fresh."""

    def __init__(self, title: str = "Datos desactualizados", message: str = "La información puede no reflejar los últimos eventos.", parent=None) -> None:
        super().__init__(title=title, description=message, parent=parent)
        self.setObjectName("staleState")
        self.setProperty("state", "STALE")
