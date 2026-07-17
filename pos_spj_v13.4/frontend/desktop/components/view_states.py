"""Canonical view-state widgets (FASE DS-3).

Every data view must be able to render one of these instead of a blank screen or
a misleading zero: LOADING, EMPTY, ERROR, NO_PERMISSION, OFFLINE, STALE,
PARTIAL_DATA. They are presentation only.
"""

from __future__ import annotations

from PyQt5.QtCore import Qt
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
        label.setObjectName("viewStateMessage")
        label.setProperty("role", "muted")
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)
        self.setAccessibleName(text)


def create_state_widget(state: str, parent=None, *, message: str | None = None) -> StateWidget:
    return StateWidget(state, parent, message=message)
