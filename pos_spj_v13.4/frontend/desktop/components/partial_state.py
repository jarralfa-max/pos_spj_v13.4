"""Canonical partial-data state component."""

from __future__ import annotations

from frontend.desktop.components.empty_state import EmptyState


class PartialState(EmptyState):
    """State shown when a view has usable data but some sources are missing."""

    def __init__(self, title: str = "Información parcial", message: str = "Algunas fuentes no entregaron datos completos.", parent=None) -> None:
        super().__init__(title=title, description=message, parent=parent)
        self.setObjectName("partialState")
        self.setProperty("state", "PARTIAL_DATA")
