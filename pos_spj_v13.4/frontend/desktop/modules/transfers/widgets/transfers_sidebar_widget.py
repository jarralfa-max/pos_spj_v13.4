"""Accessible internal navigation widget rendered from the canonical contract."""
from PyQt5.QtCore import Qt, pyqtSignal
from frontend.desktop.components.side_nav import SideNav

from ..navigation.transfers_sidebar import visible_entries


class TransfersSidebarWidget(SideNav):
    route_requested = pyqtSignal(str)

    def __init__(self, *, has_permission, badges=None, parent=None) -> None:
        super().__init__(parent, toggle_visible=False)
        self.setObjectName("moduleSidebar")
        self.setAccessibleName("Navegación de transferencias")
        self.setMinimumWidth(210)
        self.setMaximumWidth(250)
        for entry, badge in visible_entries(has_permission, badges):
            label = entry.title if badge is None else f"{entry.title} ({badge})"
            self.add_section(label, entry.icon)
            item = self.item(self.count() - 1)
            item.setData(Qt.UserRole, entry.page_id)
            item.setToolTip(entry.tooltip)
            item.setData(Qt.AccessibleDescriptionRole, entry.tooltip)
        self.currentItemChanged.connect(self._emit_route)
        if self.count():
            self.setCurrentRow(0)

    def _emit_route(self, current, _previous) -> None:
        if current is not None:
            self.route_requested.emit(str(current.data(Qt.UserRole)))
