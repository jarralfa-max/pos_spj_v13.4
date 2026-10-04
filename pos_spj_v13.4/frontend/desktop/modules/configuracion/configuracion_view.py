"""Configuración workspace: one sidebar and lazy canonical pages.
Mirrors `frontend/desktop/modules/transfers/transfers_view.py`.
"""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QStackedWidget, QWidget

from frontend.desktop.components import ViewState, create_state_widget
from frontend.desktop.components.icons import Icons
from frontend.desktop.components.module_layout import ModuleLayout
from .configuracion_routes import build_page
from .navigation.configuracion_sidebar import CONFIGURACION_NAV
from .widgets.configuracion_sidebar_widget import ConfiguracionSidebarWidget

_PERMISSION_BY_PAGE = {entry.page_id: entry.permission for entry in CONFIGURACION_NAV}


class ConfiguracionView(QWidget):
    def __init__(self, presenter, *, has_permission, badges=None, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("configuracionModule")
        self._presenter = presenter
        self._has_permission = has_permission
        self._pages = {}
        self._denied = None
        self.sidebar = ConfiguracionSidebarWidget(has_permission=has_permission, badges=badges, parent=self)
        self.stack = QStackedWidget(self)
        self.module_layout = ModuleLayout(
            self, title="Configuración", icon=Icons.SETTINGS,
            sidebar=self.sidebar, content=self.stack,
        )
        self.sidebar.route_requested.connect(self.show_route)
        if self.sidebar.count():
            self.show_route(str(self.sidebar.item(0).data(Qt.UserRole)))

    def show_route(self, page_id: str) -> None:
        """Una página sin su permiso de lectura no se construye: construirla
        ya consulta sus listados. El menú la oculta, pero una ruta pedida por
        otro camino (atajo, navegación programática) tampoco debe abrirla."""
        if not self._has_permission(_PERMISSION_BY_PAGE.get(page_id, "")):
            if self._denied is None:
                self._denied = create_state_widget(ViewState.NO_PERMISSION, self.stack)
                self.stack.addWidget(self._denied)
            self.stack.setCurrentWidget(self._denied)
            return
        page = self._pages.get(page_id)
        if page is None:
            page = build_page(page_id, self._presenter)
            self._pages[page_id] = page
            self.stack.addWidget(page)
        self.stack.setCurrentWidget(page)
        page.ensure_loaded()
