"""Canonical tooltip helper for desktop widgets."""

from __future__ import annotations

from PyQt5.QtWidgets import QWidget


class Tooltip:
    """Attach consistent, accessible tooltip text without local QSS."""

    @staticmethod
    def attach(
        widget: QWidget,
        *,
        title: str,
        description: str = "",
        shortcut: str | None = None,
        help_id: str | None = None,
    ) -> None:
        parts = [title.strip()]
        if description.strip():
            parts.append(description.strip())
        if shortcut:
            parts.append(f"Atajo: {shortcut}")
        if help_id:
            widget.setProperty("help_id", help_id)
        tooltip = "\n".join(part for part in parts if part)
        widget.setToolTip(tooltip)
        widget.setAccessibleDescription(tooltip)
