"""Canonical card system (FASE DS-3).

No module builds cards from raw styled QFrame/QGroupBox. Each card carries a
``cardVariant`` property and gets its look from the global QSS. Max one nesting
level; color always carries meaning (info/alert/danger).
"""

from __future__ import annotations

from PyQt5.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from frontend.desktop.themes.tokens import CardMetrics, Spacing, Typography


class StandardCard(QFrame):
    """General-purpose surface container."""

    card_variant = "standard"

    def __init__(self, parent=None, *, padding: int = CardMetrics.PADDING_MD) -> None:
        super().__init__(parent)
        self.setObjectName("standardCard")
        self.setProperty("cardVariant", self.card_variant)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(padding, padding, padding, padding)
        self._layout.setSpacing(Spacing.SM)

    def body(self) -> QVBoxLayout:
        return self._layout

    def add(self, widget: QWidget) -> None:
        self._layout.addWidget(widget)


class SectionCard(StandardCard):
    """Groups a titled section (forms, related info)."""

    card_variant = "section"

    def __init__(self, parent=None, *, title: str = "",
                 padding: int = CardMetrics.PADDING_MD) -> None:
        super().__init__(parent, padding=padding)
        if title:
            label = QLabel(title, self)
            label.setProperty("role", "subtitle")
            font = label.font()
            font.setPointSize(Typography.SIZE_SUBTITLE)
            font.setWeight(75)  # semibold-ish
            label.setFont(font)
            self._layout.addWidget(label)


class SummaryCard(StandardCard):
    card_variant = "summary"


class InfoCard(StandardCard):
    card_variant = "info"


class AlertCard(StandardCard):
    """Persistent risk/warning/info surface (variant carries the semantics)."""

    def __init__(self, parent=None, *, variant: str = "alert",
                 padding: int = CardMetrics.PADDING_MD) -> None:
        super().__init__(parent, padding=padding)
        self.setProperty("cardVariant", variant if variant in ("alert", "danger", "info")
                         else "alert")


class ChartCard(StandardCard):
    card_variant = "chart"
