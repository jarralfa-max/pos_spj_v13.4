"""Enterprise Mermas workspace with persistent permission-aware sidebar."""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QHBoxLayout, QStackedWidget, QWidget

from frontend.desktop.modules.losses.losses_routes import build_page
from frontend.desktop.modules.losses.widgets import LossesSidebarWidget
from frontend.desktop.themes.tokens import ResponsiveBreakpoints


class LossesView(QWidget):
    def __init__(self, *, has_permission, badges=None, page_builder=None, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("lossesModule")
        self.setAccessibleName("Módulo de mermas y pérdidas")
        self.setAccessibleDescription(
            "Espacio de trabajo para registrar, revisar y analizar pérdidas."
        )
        self.setMinimumSize(640, 480)
        self._page_builder = page_builder or build_page
        self._pages = {}
        self._active_route = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.sidebar = LossesSidebarWidget(
            has_permission=has_permission, badges=badges, parent=self)
        self.stack = QStackedWidget(self)
        layout.addWidget(self.sidebar)
        layout.addWidget(self.stack, stretch=1)
        self.sidebar.route_requested.connect(self.show_route)
        if self.sidebar.count():
            self.show_route(str(self.sidebar.item(0).data(Qt.UserRole)))

    def resizeEvent(self, event):  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self.apply_responsive_layout()

    def apply_responsive_layout(self) -> None:
        """Keep navigation usable at supported compact desktop widths."""
        self.sidebar.set_collapsed(self.width() < ResponsiveBreakpoints.COMPACT)

    @property
    def active_route(self):
        return self._active_route

    def show_route(self, page_id: str) -> None:
        page = self._pages.get(page_id)
        if page is None:
            page = self._page_builder(page_id)
            self._pages[page_id] = page
            self.stack.addWidget(page)
        self.stack.setCurrentWidget(page)
        self._active_route = page_id
        entry = next(
            (self.sidebar.item(row) for row in range(self.sidebar.count())
             if self.sidebar.item(row).data(Qt.UserRole) == page_id),
            None,
        )
        if entry is not None and self.sidebar.currentItem() is not entry:
            previous = self.sidebar.blockSignals(True)
            self.sidebar.setCurrentItem(entry)
            self.sidebar.blockSignals(previous)
        ensure_loaded = getattr(page, "ensure_loaded", None)
        if callable(ensure_loaded):
            ensure_loaded()
