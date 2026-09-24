"""Real shell contents inside a StandardWindow on simulated available desktops."""
import os
from pathlib import Path

import pytest
from PyQt5 import sip
from PyQt5.QtCore import QRect, QSettings

from frontend.desktop.components.standard_window import StandardWindow
from frontend.desktop.components.page_viewport import PageViewport
from frontend.desktop.design_system.component_gallery import build_gallery
from frontend.desktop.shell.application_shell.application_window import ApplicationWindow
from frontend.desktop.shell.router.desktop_router import DesktopRouter
from frontend.desktop.shell.routing.route_definition import RouteDefinition
from frontend.desktop.shell.routing.route_registry import RouteRegistry
from frontend.desktop.shell.routing.view_factory_registry import ViewFactoryRegistry
from frontend.desktop.shell.sidebar.global_sidebar import GlobalSidebar
from frontend.desktop.shell.sidebar.sidebar_item_view_model import SidebarItemViewModel
from frontend.desktop.themes.theme_manager import ThemeManager
from frontend.desktop.themes.tokens import ResponsiveBreakpoints
from tests.ui.shell.conftest import make_context
from tests.ui.test_standard_window_geometry import DesktopScreen, settle


@pytest.mark.parametrize("size", ResponsiveBreakpoints.VALIDATION_SIZES)
@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("density", ["compact", "comfortable", "touch"])
def test_shell_fits_available_screen_with_live_theme_and_density(qt_font_resources, ui_tmp_path, monkeypatch, size, theme, density):
    app = qt_font_resources
    settings = QSettings(str(ui_tmp_path / "window.ini"), QSettings.IniFormat)
    manager = ThemeManager(settings)
    monkeypatch.setattr(ThemeManager, "_instance", manager)
    screen = DesktopScreen(QRect(80, 40, *size))
    monkeypatch.setattr(StandardWindow, "screen", lambda self: screen)
    gallery = build_gallery(theme, density)
    routes = RouteRegistry()
    routes.register(RouteDefinition(route_id="gallery", module_id="gallery", title="Componentes JUANIS", view_factory_id="gallery"))
    factories = ViewFactoryRegistry()
    factories.register("gallery", lambda: gallery)
    router = DesktopRouter(route_registry=routes, view_factory_registry=factories, initial_context=make_context())
    sidebar = GlobalSidebar(settings=settings, settings_key="window")
    sidebar.set_items((SidebarItemViewModel("gallery", "gallery", "Componentes", "settings", "", 0, None, True),))
    window = ApplicationWindow(router=router, sidebar=sidebar)
    window.navigate("gallery")
    window.statusBar().showMessage("Lista para operar")
    try:
        window.show()
        settle(app)
        assert screen.availableGeometry().contains(window.frameGeometry())
        assert window.styleSheet() == "" and not window.windowIcon().isNull()
        assert app.property("spjTheme") == theme and app.property("spjDensity") == density
        assert window.statusBar().currentMessage() == "Lista para operar"
        viewport = gallery.findChild(PageViewport)
        assert viewport is not None and viewport.verticalScrollBar().maximum() > 0
        viewport.verticalScrollBar().setValue(viewport.verticalScrollBar().maximum())
        settle(app)
        assert viewport.verticalScrollBar().value() == viewport.verticalScrollBar().maximum()
        viewport.verticalScrollBar().setValue(0)
        settle(app)
        directory = Path(os.environ.get("SPJ_UI_VISUAL_ARTIFACTS", str(ui_tmp_path)))
        directory.mkdir(parents=True, exist_ok=True)
        assert window.grab().save(str(directory / f"{theme}-{density}-{size[0]}x{size[1]}-window.png"))
    finally:
        sip.delete(window)
