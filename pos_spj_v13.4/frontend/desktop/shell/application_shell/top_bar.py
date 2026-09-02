"""TopBar — SHELL-11.

The strip above `ContentHost`: the current route's breadcrumb (from
`RouteDefinition.breadcrumb`, SHELL-9), a compact who/where readout built
from `ApplicationContext` (SHELL-6), and a notification bell that toggles
`NotificationDrawer`. Nothing here reaches into a repository or use case —
only the values `ApplicationWindow` hands it.
"""
from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QWidget

from backend.bootstrap.application_context import ApplicationContext
from frontend.desktop.components.buttons import create_icon_button
from frontend.desktop.components.icons import Icons
from frontend.desktop.components.tooltip import apply_tooltip
from frontend.desktop.themes.tokens import Spacing


class TopBar(QWidget):
    notifications_toggled = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("topBar")

        self._breadcrumb_label = QLabel("", self)
        self._breadcrumb_label.setObjectName("topBarBreadcrumb")

        self._context_label = QLabel("", self)
        self._context_label.setObjectName("topBarContext")

        self._notifications_button = create_icon_button(
            self, icon=Icons.NOTIFICATIONS, tooltip="Notificaciones",
        )
        self._notifications_button.clicked.connect(self.notifications_toggled.emit)
        self._unread_count = 0

        layout = QHBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.SM, Spacing.LG, Spacing.SM)
        layout.setSpacing(Spacing.MD)
        layout.addWidget(self._breadcrumb_label)
        layout.addStretch(1)
        layout.addWidget(self._context_label)
        layout.addWidget(self._notifications_button)

    def set_breadcrumb(self, breadcrumb: tuple[str, ...]) -> None:
        self._breadcrumb_label.setText(" › ".join(breadcrumb))

    def set_context(self, context: ApplicationContext) -> None:
        self._context_label.setText(f"{context.branch_name} — {context.user_name}")

    def set_unread_notification_count(self, count: int) -> None:
        self._unread_count = count
        tooltip = "Notificaciones" if count <= 0 else f"Notificaciones ({count} sin leer)"
        apply_tooltip(self._notifications_button, tooltip)

    @property
    def unread_notification_count(self) -> int:
        return self._unread_count

    @property
    def breadcrumb_text(self) -> str:
        return self._breadcrumb_label.text()

    @property
    def context_text(self) -> str:
        return self._context_label.text()
