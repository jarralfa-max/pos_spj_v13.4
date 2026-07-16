"""Canonical card containers."""

from __future__ import annotations

from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget

from frontend.desktop.themes import DesktopSpacing


class StandardCard(QWidget):
    def __init__(self, title: str = "", subtitle: str = "", parent=None, *, variant: str = "default") -> None:
        super().__init__(parent)
        self.setProperty("component", "standardCard")
        self.setProperty("variant", variant)
        self.content_layout = QVBoxLayout(self)
        self.content_layout.setContentsMargins(DesktopSpacing.MD, DesktopSpacing.MD, DesktopSpacing.MD, DesktopSpacing.MD)
        self.content_layout.setSpacing(DesktopSpacing.SM)
        if title:
            title_label = QLabel(title, self)
            title_label.setObjectName("cardTitle")
            self.content_layout.addWidget(title_label)
        if subtitle:
            subtitle_label = QLabel(subtitle, self)
            subtitle_label.setObjectName("cardSubtitle")
            subtitle_label.setWordWrap(True)
            self.content_layout.addWidget(subtitle_label)


class SectionCard(StandardCard):
    pass


class SummaryCard(StandardCard):
    pass


class AlertCard(StandardCard):
    pass


class ChartCard(StandardCard):
    pass
