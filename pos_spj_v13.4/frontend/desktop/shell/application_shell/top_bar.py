"""TopBar — SHELL-11.

The strip above `ContentHost`: the current route's breadcrumb (from
`RouteDefinition.breadcrumb`, SHELL-9), a compact who/where readout built
from `ApplicationContext` (SHELL-6), and a notification bell that toggles
`NotificationDrawer`. Nothing here reaches into a repository or use case —
only the values `ApplicationWindow` hands it.
"""
from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QAction, QHBoxLayout, QLabel, QMenu, QSizePolicy, QVBoxLayout, QWidget

from backend.bootstrap.application_context import ApplicationContext
from frontend.desktop.components.buttons import create_ghost_button, create_icon_button
from frontend.desktop.components.icons import IconProvider, Icons
from frontend.desktop.components.status_badge import StatusBadge
from frontend.desktop.components.tooltip import apply_tooltip
from frontend.desktop.themes.tokens import Spacing


class TopBar(QWidget):
    notifications_toggled = pyqtSignal()
    settings_requested = pyqtSignal()
    logout_requested = pyqtSignal()
    exit_requested = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("topBar")

        self._breadcrumb_label = QLabel("", self)
        self._breadcrumb_label.setObjectName("topBarBreadcrumb")
        self._breadcrumb_label.setMinimumWidth(0)
        self._breadcrumb_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

        self._context_label = QLabel("", self)
        self._context_label.setObjectName("topBarContext")
        self._context_label.setWordWrap(True)
        self._context_label.setMaximumWidth(360)
        self._session_badge = StatusBadge("Conectado", status="success")
        self._session_badge.setAccessibleName("Estado de sesión: Conectado")

        self.file_menu = QMenu("Archivo", self)
        self.logout_action = QAction("Cerrar sesión", self)
        IconProvider.bind(self.logout_action, Icons.LOGOUT)
        self.logout_action.triggered.connect(self.logout_requested.emit)
        self.exit_action = QAction("Salir", self)
        IconProvider.bind(self.exit_action, Icons.CLOSE)
        self.exit_action.triggered.connect(self.exit_requested.emit)
        self.file_menu.addAction(self.logout_action)
        self.file_menu.addSeparator()
        self.file_menu.addAction(self.exit_action)
        self._file_button = create_ghost_button(self, "Archivo")
        self._file_button.setMenu(self.file_menu)

        self._settings_button = create_icon_button(self, icon=Icons.SETTINGS, tooltip="Configuración")
        self._settings_button.clicked.connect(self.settings_requested.emit)

        self._notifications_button = create_icon_button(
            self, icon=Icons.NOTIFICATIONS, tooltip="Notificaciones",
        )
        self._notifications_button.clicked.connect(self.notifications_toggled.emit)
        self._notification_badge = StatusBadge("", status="danger")
        self._notification_badge.setObjectName("notificationCountBadge")
        self._notification_badge.setVisible(False)
        self._unread_count = 0

        user_layout = QVBoxLayout()
        user_layout.setContentsMargins(0, 0, 0, 0)
        user_layout.setSpacing(0)
        user_layout.addWidget(self._context_label)
        user_layout.addWidget(self._session_badge)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.SM, Spacing.LG, Spacing.SM)
        layout.setSpacing(Spacing.MD)
        layout.addWidget(self._file_button)
        layout.addWidget(self._breadcrumb_label, 1)
        layout.addWidget(self._notifications_button)
        layout.addWidget(self._notification_badge)
        layout.addWidget(self._settings_button)
        layout.addLayout(user_layout)

    def set_breadcrumb(self, breadcrumb: tuple[str, ...]) -> None:
        self._breadcrumb_label.setText(" › ".join(breadcrumb))
        self._breadcrumb_label.setToolTip(self._breadcrumb_label.text())
        self._breadcrumb_label.setAccessibleName(self._breadcrumb_label.text())

    def set_context(self, context: ApplicationContext) -> None:
        self._context_label.setText(f"{context.user_name}\n{context.branch_name}")
        self._context_label.setToolTip(f"{context.user_name} — {context.branch_name}")
        metrics = self._context_label.fontMetrics()
        self._context_label.setMinimumWidth(min(
            self._context_label.maximumWidth(),
            max(metrics.horizontalAdvance(context.user_name), metrics.horizontalAdvance(context.branch_name)),
        ))
        self._context_label.setAccessibleName(f"Usuario: {context.user_name}. Sucursal: {context.branch_name}")
        self.set_session_state("offline" if context.offline_status == "OFFLINE" else "connected")

    def set_session_state(self, state: str) -> None:
        states = {
            "connected": ("Conectado", "success"),
            "offline": ("Sin conexión", "warning"),
            "locked": ("Sesión bloqueada", "warning"),
            "expiring": ("Sesión próxima a vencer", "warning"),
        }
        if state not in states:
            raise ValueError(f"Unknown session UI state: {state}")
        label, status = states[state]
        self._session_badge.setText(label)
        self._session_badge.set_status(status)
        self._session_badge.setAccessibleName(f"Estado de sesión: {label}")

    def set_unread_notification_count(self, count: int) -> None:
        count = max(0, int(count))
        self._unread_count = count
        self._notification_badge.setText(str(count) if count <= 99 else "99+")
        self._notification_badge.setVisible(count > 0)
        self._notification_badge.setAccessibleName(f"{count} notificaciones sin leer")
        tooltip = "Notificaciones" if count <= 0 else f"Notificaciones ({count} sin leer)"
        apply_tooltip(self._notifications_button, tooltip)
        self._notifications_button.setAccessibleName(tooltip)

    @property
    def session_text(self) -> str:
        return self._session_badge.text()

    @property
    def unread_notification_count(self) -> int:
        return self._unread_count

    @property
    def breadcrumb_text(self) -> str:
        return self._breadcrumb_label.text()

    @property
    def context_text(self) -> str:
        return self._context_label.text()
