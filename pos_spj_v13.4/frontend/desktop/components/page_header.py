"""Canonical PageHeader (FASE DS-3).

Every page starts with one PageHeader. It owns the title/subtitle and the page's
action buttons (one primary, up to two secondary; the rest belong in an overflow
menu handled by the page). Styled only via the global QSS (`#pageHeader`).
"""

from __future__ import annotations

from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from frontend.desktop.components.icons import icon_accessible_name
from frontend.desktop.themes.tokens import Spacing


class PageHeader(QFrame):
    def __init__(self, parent=None, *, title: str = "", subtitle: str = "",
                 icon: str | None = None, compact: bool = False,
                 actions: list | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("pageHeader")

        root = QHBoxLayout(self)
        margin_v = Spacing.SM if compact else Spacing.MD
        root.setContentsMargins(0, margin_v, 0, margin_v)
        root.setSpacing(Spacing.MD)

        text_col = QVBoxLayout()
        text_col.setSpacing(Spacing.XXS)
        self._title = QLabel(title, self)
        self._title.setObjectName("pageHeaderTitle")
        if icon:
            self._title.setAccessibleName(f"{icon_accessible_name(icon)}: {title}")
        text_col.addWidget(self._title)

        self._subtitle = QLabel(subtitle, self)
        self._subtitle.setObjectName("pageHeaderSubtitle")
        self._subtitle.setWordWrap(True)
        self._subtitle.setVisible(bool(subtitle))
        text_col.addWidget(self._subtitle)
        root.addLayout(text_col, stretch=1)

        self._actions_row = QHBoxLayout()
        self._actions_row.setSpacing(Spacing.SM)
        self._actions_host = QWidget(self)
        self._actions_host.setLayout(self._actions_row)
        root.addWidget(self._actions_host)

        for action in (actions or []):
            self.add_action(action)

    def add_action(self, widget: QWidget) -> None:
        """Append an action button to the header's right side."""
        self._actions_row.addWidget(widget)

    def set_title(self, title: str) -> None:
        self._title.setText(title)

    def set_subtitle(self, subtitle: str) -> None:
        self._subtitle.setText(subtitle)
        self._subtitle.setVisible(bool(subtitle))
