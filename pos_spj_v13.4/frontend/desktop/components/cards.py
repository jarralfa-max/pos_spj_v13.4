"""Canonical card system (FASE DS-3).

No module builds cards from raw styled QFrame/QGroupBox. Each card carries a
``cardVariant`` property and gets its look from the global QSS. Max one nesting
level; color always carries meaning (info/alert/danger).
"""

from __future__ import annotations

from PyQt5.QtCore import Qt, QPropertyAnimation, pyqtSignal
from PyQt5.QtWidgets import QApplication, QFrame, QGraphicsDropShadowEffect, QLabel, QVBoxLayout, QWidget

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


class InteractiveSummaryCard(SummaryCard):
    """Keyboard/touch activation and stationary elevation for selectable cards."""
    activated = pyqtSignal()

    def __init__(self, parent=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setProperty("interactive", True)
        self.setProperty("selected", False)
        self._pressed = False
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setOffset(0, 1)
        self._shadow.setBlurRadius(0)
        self.setGraphicsEffect(self._shadow)
        self._animation = QPropertyAnimation(self._shadow, b"blurRadius", self)
        self._animation.setDuration(140)

    def set_selected(self, selected):
        self.setProperty("selected", bool(selected))
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def enterEvent(self, event):
        from frontend.desktop.themes.theme_manager import ThemeManager
        from PyQt5.QtGui import QColor
        self._shadow.setColor(QColor(ThemeManager.instance().colors().BORDER_STRONG))
        self._animate(12)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._animate(0)
        self._pressed = False
        super().leaveEvent(event)

    def _animate(self, value):
        self._animation.stop()
        if QApplication.instance().property("reducedMotion"):
            self._shadow.setBlurRadius(value)
            return
        self._animation.setStartValue(self._shadow.blurRadius())
        self._animation.setEndValue(value)
        self._animation.start()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.isEnabled():
            self._pressed = True
            self.setFocus(Qt.MouseFocusReason)
            self._animate(0)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self._pressed and event.button() == Qt.LeftButton:
            self._pressed = False
            if self.rect().contains(event.pos()):
                self.activated.emit()
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            if not event.isAutoRepeat() and self.isEnabled():
                self.activated.emit()
            event.accept()
        else:
            super().keyPressEvent(event)


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
