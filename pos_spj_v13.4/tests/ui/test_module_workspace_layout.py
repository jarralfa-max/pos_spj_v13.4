"""Real module shells share Pricing geometry; business page bodies are isolated."""
from importlib import import_module

import pytest
from PyQt5 import sip
from PyQt5.QtCore import QEvent, Qt
from PyQt5.QtWidgets import QLabel, QLineEdit, QVBoxLayout, QWidget

from frontend.desktop.themes.theme_manager import ThemeManager


MODULES = {
    "products": ("ProductsView", "Productos"),
    "inventory": ("InventoryView", "Inventario"),
    "finance": ("FinanceView", "Finanzas"),
    "hr": ("HRView", "Recursos Humanos"),
    "losses": ("LossesView", "Mermas y Pérdidas"),
    "meat_processing": ("MeatProcessingView", "Producción"),
    "transfers": ("TransfersView", "Transferencias"),
    "configuracion": ("ConfiguracionView", "Configuración"),
    "orders_delivery": ("OrdersDeliveryView", "Pedidos y Reparto"),
    "business_intelligence": ("BusinessIntelligenceView", "Inteligencia de Negocios"),
}


class PageBody(QWidget):
    def __init__(self, _presenter=None, parent=None):
        super().__init__(parent)
        self.loads = 0
        self.input = QLineEdit(self)
        layout = QVBoxLayout(self)
        layout.addWidget(self.input)

    def ensure_loaded(self):
        self.loads += 1

    def refresh(self):
        self.loads += 1


def build_workspace(module_name, monkeypatch):
    """Keep the real navigation, permissions, caching and page-stack wiring."""
    module = import_module(f"frontend.desktop.modules.{module_name}.{module_name}_view")
    view_class = getattr(module, MODULES[module_name][0])
    if module_name in {"finance", "hr"}:
        monkeypatch.setattr(module, "_NAVIGATION", [
            (*entry[:2], PageBody, *entry[3:]) for entry in module._NAVIGATION
        ])
        view = view_class(object())
        return view, view._nav, view._stack
    if module_name in {"products", "inventory"}:
        navigation = import_module(f"frontend.desktop.modules.{module_name}.navigation")
        entries = getattr(navigation, f"{module_name.upper()}_NAV")
        view = view_class(object(), [(PageBody, entry.title) for entry in entries])
        return view, view.nav, view.stack
    if module_name in {"transfers", "configuracion"}:
        monkeypatch.setattr(module, "build_page", lambda _route, _presenter: PageBody())
        view = view_class(object(), has_permission=lambda _permission: True)
    else:
        view = view_class(has_permission=lambda _permission: True,
                          page_builder=lambda _route: PageBody())
    return view, view.sidebar, view.stack


def _settle(app):
    for _ in range(4):
        app.processEvents()


@pytest.mark.parametrize("module_name", MODULES)
@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("density", ["compact", "comfortable", "touch"])
def test_workspace_matches_pricing_and_preserves_navigation_on_resize(
        qt_font_resources, monkeypatch, module_name, theme, density):
    app = qt_font_resources
    manager = ThemeManager()
    monkeypatch.setattr(ThemeManager, "_instance", manager)
    manager.apply(app, theme, density=density)
    view, nav, stack = build_workspace(module_name, monkeypatch)
    try:
        view.resize(1366, 768)
        view.show()
        _settle(app)
        header = view.module_layout.header
        viewport = view.module_layout.viewport
        assert header.findChild(QLabel, "pageHeaderTitle").text() == MODULES[module_name][1]
        assert (header.x(), header.y(), header.width()) == (20, 16, view.width() - 40)
        assert nav.x() == header.x()
        assert nav.y() == header.geometry().bottom() + 13
        assert viewport.y() == nav.y()
        assert viewport.x() == nav.geometry().right() + 17
        assert (nav.minimumWidth(), nav.maximumWidth()) == (180, 240)
        assert not viewport.isAncestorOf(nav)
        assert not viewport.isAncestorOf(header)
        assert viewport.widget() is stack

        rows = [row for row in range(nav.count()) if not nav.item(row).data(nav._GROUP_ROLE)]
        first_page = stack.currentWidget()
        first_input = first_page.findChild(QLineEdit)
        first_input.setText("Captura pendiente")
        nav.select(rows[-1])
        assert stack.currentWidget() is not first_page
        nav.select(rows[0])
        assert stack.currentWidget() is first_page
        assert first_input.text() == "Captura pendiente"
        destinations = [
            (nav.item(row).data(Qt.UserRole), nav.item(row).data(nav._ICON_ROLE))
            for row in rows
        ]

        for collapsed in (True, False):
            nav.set_collapsed(collapsed)
            for width in (1024, 1440, 1366):
                view.resize(width, 768)
                _settle(app)
                assert nav.collapsed is collapsed
                assert (nav.minimumWidth(), nav.maximumWidth()) == (
                    (60, 64) if collapsed else (180, 240))
                assert view.width() == width
                assert stack.currentWidget() is first_page
                assert first_input.text() == "Captura pendiente"
                assert destinations == [
                    (nav.item(row).data(Qt.UserRole), nav.item(row).data(nav._ICON_ROLE))
                    for row in rows
                ]

        # Oversized page content scrolls without moving the title or navigation.
        first_page.setMinimumSize(1600, 1000)
        view.resize(1024, 768)
        _settle(app)
        assert view.width() == 1024
        header_geometry, nav_geometry = header.geometry(), nav.geometry()
        for scrollbar in (viewport.horizontalScrollBar(), viewport.verticalScrollBar()):
            assert scrollbar.maximum() > 0
            scrollbar.setValue(scrollbar.maximum())
        _settle(app)
        assert header.geometry() == header_geometry
        assert nav.geometry() == nav_geometry
        assert first_input.text() == "Captura pendiente"
    finally:
        view.close()
        sip.delete(view)
        app.sendPostedEvents(None, QEvent.DeferredDelete)
        _settle(app)
