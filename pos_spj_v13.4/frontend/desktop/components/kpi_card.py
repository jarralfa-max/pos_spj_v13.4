"""Canonical KPI card component."""

from __future__ import annotations

from dataclasses import dataclass

from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget

from frontend.desktop.components.tooltip import Tooltip
from frontend.desktop.themes import DesktopSpacing


@dataclass(frozen=True, slots=True)
class KPIDTO:
    key: str
    title: str
    value: str
    icon: str
    variant: str = "neutral"
    subtitle: str = ""
    tooltip: str = ""


class KPICard(QWidget):
    """Read-only KPI card. Values must be prepared by a presenter/query service."""

    def __init__(self, dto: KPIDTO, parent=None) -> None:
        super().__init__(parent)
        self.setProperty("component", "kpiCard")
        self.setProperty("variant", dto.variant)
        self.setProperty("icon", dto.icon)
        self.setMinimumHeight(96)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(DesktopSpacing.MD, DesktopSpacing.MD, DesktopSpacing.MD, DesktopSpacing.MD)
        layout.setSpacing(DesktopSpacing.XS)
        self._title = QLabel(dto.title, self)
        self._title.setObjectName("kpiTitle")
        self._title.setWordWrap(True)
        self._value = QLabel(dto.value, self)
        self._value.setObjectName("kpiValue")
        self._value.setAccessibleName(dto.title)
        self._subtitle = QLabel(dto.subtitle, self)
        self._subtitle.setObjectName("kpiSubtitle")
        self._subtitle.setWordWrap(True)
        layout.addWidget(self._title)
        layout.addWidget(self._value)
        layout.addWidget(self._subtitle)
        Tooltip.attach(self, title=dto.title, description=dto.tooltip or dto.subtitle)

    def set_value(self, value: str) -> None:
        self._value.setText(value)
