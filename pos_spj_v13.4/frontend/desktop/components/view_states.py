"""Canonical view-state widgets (FASE DS-3).

Every data view must be able to render one of these instead of a blank screen or
a misleading zero: LOADING, EMPTY, ERROR, NO_PERMISSION, OFFLINE, STALE,
PARTIAL_DATA. They are presentation only.
"""

from __future__ import annotations

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget

from frontend.desktop.i18n.es_mx import ui
from frontend.desktop.themes.tokens import Spacing


class ViewState:
    LOADING = "LOADING"
    READY = "READY"
    EMPTY = "EMPTY"
    ERROR = "ERROR"
    NO_PERMISSION = "NO_PERMISSION"
    OFFLINE = "OFFLINE"
    STALE = "STALE"
    PARTIAL_DATA = "PARTIAL_DATA"


_DEFAULT_MESSAGE = {
    ViewState.LOADING: ui("state.loading"),
    ViewState.EMPTY: ui("state.empty"),
    ViewState.ERROR: ui("state.error"),
    ViewState.NO_PERMISSION: ui("state.no_permission"),
    ViewState.OFFLINE: ui("state.offline"),
    ViewState.STALE: ui("state.stale"),
    ViewState.PARTIAL_DATA: ui("state.partial"),
}


class StateWidget(QWidget):
    """A centered, accessible placeholder for a non-ready view state."""

    def __init__(self, state: str, parent=None, *, message: str | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("viewState")
        self.setProperty("state", state)
        text = message or _DEFAULT_MESSAGE.get(state, "")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.XL, Spacing.XXL, Spacing.XL, Spacing.XXL)
        layout.setAlignment(Qt.AlignCenter)
        label = QLabel(text, self)
        self.message_label = label
        label.setObjectName("viewStateMessage")
        label.setProperty("role", "muted")
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)
        self.setAccessibleName(text)


def create_state_widget(state: str, parent=None, *, message: str | None = None) -> StateWidget:
    return StateWidget(state, parent, message=message)


class LoadingState(StateWidget):
    def __init__(self, parent=None, *, message=None):
        super().__init__(ViewState.LOADING, parent, message=message)


class EmptyState(StateWidget):
    def __init__(self, parent=None, *, message=None):
        super().__init__(ViewState.EMPTY, parent, message=message)


class ErrorState(StateWidget):
    def __init__(self, parent=None, *, message=None):
        super().__init__(ViewState.ERROR, parent, message=message)


class Toast(StateWidget):
    """Inline nonmodal feedback. The caller places it in its page layout."""
    def __init__(self, parent=None):
        super().__init__(ViewState.READY, parent)
        self.setObjectName("toast")
        self.layout().setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)
        self.hide()

    def show_message(self, message: str, *, timeout_ms: int = 4000):
        self.message_label.setText(message)
        self.setAccessibleName(message)
        self.show()
        self._timer.start(max(0, timeout_ms))
