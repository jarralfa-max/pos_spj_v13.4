"""Enterprise Transfers workspace: one sidebar and lazy canonical pages."""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QStackedWidget, QWidget

from frontend.desktop.components.icons import Icons
from frontend.desktop.components.module_layout import ModuleLayout
from .transfers_routes import build_page
from .widgets.transfers_sidebar_widget import TransfersSidebarWidget


class TransfersView(QWidget):
    def __init__(self, presenter, *, has_permission=lambda _permission: True,
                 badges=None, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("transfersModule")
        self._presenter = presenter
        self._pages = {}
        self.sidebar = TransfersSidebarWidget(
            has_permission=has_permission, badges=badges, parent=self)
        self.stack = QStackedWidget(self)
        self.module_layout = ModuleLayout(
            self, title="Transferencias", icon=Icons.TRANSFERS,
            sidebar=self.sidebar, content=self.stack,
        )
        self.sidebar.route_requested.connect(self.show_route)
        if self.sidebar.count():
            self.show_route(str(self.sidebar.item(0).data(Qt.UserRole)))

    def show_route(self, page_id: str) -> None:
        page = self._pages.get(page_id)
        if page is None:
            page = build_page(page_id, self._presenter)
            self._pages[page_id] = page
            self.stack.addWidget(page)
        self.stack.setCurrentWidget(page)
        page.ensure_loaded()
