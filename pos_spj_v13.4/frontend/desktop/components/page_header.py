"""Canonical desktop page header."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PyQt5.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from frontend.desktop.components.buttons import StandardButton
from frontend.desktop.components.tooltip import Tooltip
from frontend.desktop.themes import DesktopSpacing


@dataclass(frozen=True, slots=True)
class PageAction:
    text: str
    callback: Callable[[], None]
    variant: str = "secondary"
    tooltip: str = ""


class PageHeader(QWidget):
    """Shared header with title, subtitle and controlled actions."""

    def __init__(
        self,
        *,
        title: str,
        subtitle: str,
        icon: str,
        actions: tuple[PageAction, ...] = (),
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setProperty("component", "pageHeader")
        self.setProperty("icon", icon)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(DesktopSpacing.MD)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(DesktopSpacing.XS)
        title_label = QLabel(title, self)
        title_label.setObjectName("pageTitle")
        title_label.setWordWrap(True)
        subtitle_label = QLabel(subtitle, self)
        subtitle_label.setObjectName("pageSubtitle")
        subtitle_label.setWordWrap(True)
        Tooltip.attach(title_label, title=title, description=subtitle)
        text_layout.addWidget(title_label)
        text_layout.addWidget(subtitle_label)
        layout.addLayout(text_layout, 1)

        for index, action in enumerate(actions[:3]):
            button = StandardButton(
                action.text,
                self,
                variant="primary" if index == 0 and action.variant == "primary" else action.variant,
                tooltip=action.tooltip,
            )
            button.clicked.connect(action.callback)  # type: ignore[arg-type]
            layout.addWidget(button)
