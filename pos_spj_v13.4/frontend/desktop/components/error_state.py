"""Canonical error state component."""

from __future__ import annotations

from frontend.desktop.components.empty_state import EmptyState


class ErrorState(EmptyState):
    """Readable non-technical error state for views and cards."""

    def __init__(self, title: str = "No se pudo cargar la información", message: str = "Intenta nuevamente o contacta soporte.", parent=None) -> None:
        super().__init__(title=title, description=message, parent=parent)
        self.setObjectName("errorState")
        self.setProperty("state", "ERROR")
