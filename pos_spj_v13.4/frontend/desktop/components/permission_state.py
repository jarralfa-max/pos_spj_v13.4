"""Canonical no-permission state component."""

from __future__ import annotations

from frontend.desktop.components.empty_state import EmptyState


class PermissionState(EmptyState):
    """State shown when the current user cannot access a view or action."""

    def __init__(self, title: str = "Sin permiso", message: str = "Tu usuario no tiene permiso para ver esta información.", parent=None) -> None:
        super().__init__(title=title, description=message, parent=parent)
        self.setObjectName("permissionState")
        self.setProperty("state", "NO_PERMISSION")
