"""Canonical offline/connectivity state component."""

from __future__ import annotations

from frontend.desktop.components.empty_state import EmptyState


class OfflineState(EmptyState):
    """State shown when a data source is not reachable."""

    def __init__(self, title: str = "Sin conexión", message: str = "Algunas fuentes no están disponibles. Revisa la conectividad.", parent=None) -> None:
        super().__init__(title=title, description=message, parent=parent)
        self.setObjectName("offlineState")
        self.setProperty("state", "OFFLINE")
