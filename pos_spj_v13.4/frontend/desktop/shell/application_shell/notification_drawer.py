"""NotificationDrawer — SHELL-11.

A slide-out panel of `NotificationItem`s the shell shows/hides via
`TopBar`'s bell button. There's no shell-wide notification service yet to
source these from — same "declare the shape, wire the backend later"
deferral SHELL-8's empty `view_factories` and SHELL-9's routes-without-real-
views use — so this class only manages an in-memory list handed to it one
item at a time. Wiring it to a real event stream (EventBus priority-10
"Notificaciones secundarias") is future work.

Tracks its own `is_open` flag rather than relying on `QWidget.isVisible()`
— a widget that's never been shown by a real window manager reports
`isVisible() == False` regardless of `setVisible(True)` (the same
headless-testing pitfall hit in SHELL-2/SHELL-7), so open/closed state
needs to be independently queryable in tests that never call `.show()`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from frontend.desktop.components.buttons import create_icon_button
from frontend.desktop.components.icons import Icons
from frontend.desktop.themes.tokens import Spacing


@dataclass(frozen=True)
class NotificationItem:
    notification_id: str
    title: str
    message: str
    created_at: datetime
    read: bool = False

    def with_read(self, read: bool) -> "NotificationItem":
        return NotificationItem(
            notification_id=self.notification_id, title=self.title, message=self.message,
            created_at=self.created_at, read=read,
        )


class NotificationDrawer(QWidget):
    notification_activated = pyqtSignal(str)
    unread_count_changed = pyqtSignal(int)
    closed = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("notificationDrawer")
        self._items: dict[str, NotificationItem] = {}
        self._open = False

        title = QLabel("Notificaciones", self)
        title.setObjectName("notificationDrawerTitle")
        close_button = create_icon_button(self, icon=Icons.CLOSE, tooltip="Cerrar")
        close_button.clicked.connect(self.close)

        header = QHBoxLayout()
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(close_button)

        self._list = QListWidget(self)
        self._list.itemActivated.connect(self._on_item_activated)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
        layout.setSpacing(Spacing.SM)
        layout.addLayout(header)
        layout.addWidget(self._list)

        self.setVisible(False)

    def add_notification(self, item: NotificationItem) -> None:
        self._items[item.notification_id] = item
        self._rebuild()

    def mark_read(self, notification_id: str) -> None:
        item = self._items.get(notification_id)
        if item is not None and not item.read:
            self._items[notification_id] = item.with_read(True)
            self._rebuild()

    def clear(self) -> None:
        self._items.clear()
        self._rebuild()

    def unread_count(self) -> int:
        return sum(1 for item in self._items.values() if not item.read)

    def all_notifications(self) -> tuple[NotificationItem, ...]:
        return tuple(self._items.values())

    @property
    def is_open(self) -> bool:
        return self._open

    def open(self) -> None:
        self._open = True
        self.setVisible(True)

    def close(self) -> None:
        if not self._open:
            return
        self._open = False
        self.setVisible(False)
        self.closed.emit()

    def toggle(self) -> None:
        self.close() if self._open else self.open()

    def _rebuild(self) -> None:
        self._list.clear()
        for item in self._items.values():
            list_item = QListWidgetItem(item.title)
            font = list_item.font()
            font.setWeight(QFont.Normal if item.read else QFont.Bold)
            list_item.setFont(font)
            list_item.setData(Qt.UserRole, item.notification_id)
            list_item.setToolTip(item.message)
            self._list.addItem(list_item)
        self.unread_count_changed.emit(self.unread_count())

    def _on_item_activated(self, list_item: QListWidgetItem) -> None:
        notification_id = list_item.data(Qt.UserRole)
        self.mark_read(notification_id)
        self.notification_activated.emit(notification_id)
