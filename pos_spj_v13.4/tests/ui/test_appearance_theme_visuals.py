"""Exercise the terminal theme selector inside the real application shell."""
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PyQt5.QtCore import QEvent, QPoint, QRect, QSettings

from frontend.desktop.modules.configuracion.pages.apariencia_page import AparienciaPage
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


@pytest.mark.parametrize("size", ResponsiveBreakpoints.VALIDATION_SIZES)
@pytest.mark.parametrize("density", ["comfortable", "touch"])
def test_theme_selector_is_reachable_and_preserves_live_page(qt_font_resources, ui_tmp_path, monkeypatch, size, density):
    app = qt_font_resources
    settings = QSettings(str(ui_tmp_path / "appearance.ini"), QSettings.IniFormat)
    manager = ThemeManager(settings)
    monkeypatch.setattr(ThemeManager, "_instance", manager)
    manager.apply(app, "light", density=density)
    presenter = MagicMock()
    presenter.load_page.return_value = SimpleNamespace(
        columns=(SimpleNamespace(title="Tema", kind="text"),),
        rows=(), empty_message="No hay temas registrados.",
    )
    presenter.list_themes.return_value = ()
    presenter.list_density_profiles.return_value = ()
    presenter.list_appearance_preferences.return_value = ()
    page = AparienciaPage(presenter)
    page.ensure_loaded()
    page.search.setText("Referencia en captura")
    registry = RouteRegistry()
    registry.register(RouteDefinition(route_id="appearance", module_id="configuracion",
                                      title="Apariencia", view_factory_id="appearance"))
    factories = ViewFactoryRegistry()
    factories.register("appearance", lambda: page)
    router = DesktopRouter(route_registry=registry, view_factory_registry=factories,
                           initial_context=make_context())
    sidebar = GlobalSidebar(settings=settings, settings_key="visual")
    sidebar.set_items((SidebarItemViewModel("configuracion", "appearance", "Configuración", "settings", "", 0, None, True),))
    window = ApplicationWindow(router=router, sidebar=sidebar)
    window.navigate("appearance")
    try:
        window.show()
        window.resize(*size)
        for theme in ("light", "dark"):
            page.theme_selector.setCurrentIndex(page.theme_selector.findData(theme))
            for _ in range(4):
                app.processEvents()
            assert (window.width(), window.height()) == size
            assert app.property("spjTheme") == theme
            assert app.property("spjDensity") == density
            assert page.search.text() == "Referencia en captura"
            assert page.theme_selector.isVisible()
            assert page.theme_selector.visibleRegion().boundingRect() == page.theme_selector.rect()
            bounds = QRect(page.theme_selector.mapTo(window, QPoint()), page.theme_selector.size())
            assert window.rect().contains(bounds)
            artifacts = Path(os.environ.get("SPJ_UI_VISUAL_ARTIFACTS", str(ui_tmp_path)))
            artifacts.mkdir(parents=True, exist_ok=True)
            image = window.grab()
            assert not image.isNull()
            assert image.save(str(artifacts / f"{theme}-{density}-{size[0]}x{size[1]}-appearance.png"))
        assert settings.value("appearance/theme") == "dark"
        presenter.create_theme.assert_not_called()
        presenter.update_theme.assert_not_called()
    finally:
        window.close()
        window.deleteLater()
        app.sendPostedEvents(None, QEvent.DeferredDelete)
