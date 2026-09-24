"""Change terminal density on a live appearance page at every supported size."""

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PyQt5.QtCore import QEvent, QPoint, QRect, QSettings, Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QAbstractItemView

from frontend.desktop.modules.configuracion.pages.apariencia_page import AparienciaPage
from frontend.desktop.shell.application_shell.application_window import ApplicationWindow
from frontend.desktop.shell.router.desktop_router import DesktopRouter
from frontend.desktop.shell.routing.route_definition import RouteDefinition
from frontend.desktop.shell.routing.route_registry import RouteRegistry
from frontend.desktop.shell.routing.view_factory_registry import ViewFactoryRegistry
from frontend.desktop.shell.sidebar.global_sidebar import GlobalSidebar
from frontend.desktop.shell.sidebar.sidebar_item_view_model import SidebarItemViewModel
from frontend.desktop.themes.theme_manager import ThemeManager
from frontend.desktop.themes.tokens import ResponsiveBreakpoints, density_metrics
from tests.ui.shell.conftest import make_context
from tests.ui.test_standard_window_geometry import DesktopScreen


_THEME_ID = "01988900-6e4e-7000-8000-000000000071"
_PROFILES = (("compact", "Compacta"), ("comfortable", "Cómoda"), ("touch", "Táctil"))


def _settle(app):
    for _ in range(4):
        app.processEvents()
    QTest.qWait(10)


def _select_density_with_mouse(app, selector, density):
    """Exercise the visible selector and its actual popup hit targets."""
    QTest.mouseClick(selector, Qt.LeftButton, pos=selector.rect().center())
    _settle(app)
    view = selector.view()
    assert view.isVisible()
    index = selector.model().index(selector.findData(density), 0)
    assert index.isValid()
    # The native popup blocks a release during the double-click interval and
    # may scroll to align the previously selected option with the control.
    QTest.qWait(app.doubleClickInterval() + 50)
    view.scrollTo(index, QAbstractItemView.PositionAtCenter)
    _settle(app)
    row = view.visualRect(index)
    # Native QComboBox delegates can return a row wider than their popup. Use
    # the visible hit area, while requiring the whole label and row height.
    target = row.intersected(view.viewport().rect())
    assert target.height() == row.height()
    assert target.height() >= density_metrics().input_height
    assert target.width() >= view.fontMetrics().horizontalAdvance(str(index.data()))
    QTest.mouseClick(view.viewport(), Qt.LeftButton, pos=target.center())
    _settle(app)
    assert selector.currentData() == density
    assert not view.isVisible()


@pytest.mark.parametrize("size", ResponsiveBreakpoints.VALIDATION_SIZES)
@pytest.mark.parametrize("theme", ("light", "dark"))
def test_density_profiles_preserve_live_page_at_supported_sizes(
    qt_font_resources, ui_tmp_path, monkeypatch, size, theme,
):
    app = qt_font_resources
    settings_path = str(ui_tmp_path / "density.ini")
    settings = QSettings(settings_path, QSettings.IniFormat)
    manager = ThemeManager(settings)
    monkeypatch.setattr(ThemeManager, "_instance", manager)
    manager.apply(app, theme, density="comfortable")
    presenter = MagicMock()
    presenter.load_page.return_value = SimpleNamespace(
        columns=(SimpleNamespace(title="Tema", kind="text"),),
        rows=(SimpleNamespace(entity_id=_THEME_ID, cells=("JUANIS",)),),
        empty_message="No hay temas registrados.",
    )
    presenter.list_themes.return_value = (SimpleNamespace(entity_id=_THEME_ID, name="JUANIS"),)
    presenter.list_design_tokens_for_theme.return_value = ()
    presenter.list_density_profiles.return_value = ()
    presenter.list_appearance_preferences.return_value = ()
    page = AparienciaPage(presenter)
    page.ensure_loaded()
    # Finish the legitimate search before tracking density-only activity.
    page.search.set_debounce_ms(0)
    page.search.setText("JUANIS")
    page.table.selectRow(0)
    selected_table = page.table
    calls_before_density = list(presenter.mock_calls)

    registry = RouteRegistry()
    registry.register(RouteDefinition(
        route_id="appearance", module_id="configuracion", title="Apariencia",
        view_factory_id="appearance",
    ))
    factories = ViewFactoryRegistry()
    factories.register("appearance", lambda: page)
    router = DesktopRouter(
        route_registry=registry, view_factory_registry=factories, initial_context=make_context(),
    )
    sidebar = GlobalSidebar(settings=settings, settings_key="density-visual")
    sidebar.set_items((SidebarItemViewModel(
        "configuracion", "appearance", "Configuración", "settings", "", 0, None, True,
    ),))
    window = ApplicationWindow(router=router, sidebar=sidebar)
    screen = DesktopScreen(QRect(0, 0, *size))
    monkeypatch.setattr(window, "screen", lambda: screen)
    window.navigate("appearance")
    try:
        window.show()
        window.resize(*size)
        _settle(app)
        selector = page.density_selector
        assert tuple((selector.itemData(i), selector.itemText(i)) for i in range(selector.count())) == _PROFILES

        for density in ("comfortable", "touch", "compact"):
            _select_density_with_mouse(app, selector, density)
            metrics = density_metrics(density)
            assert screen.availableGeometry().contains(window.frameGeometry())
            assert manager.theme == app.property("spjTheme") == theme
            assert manager.density == app.property("spjDensity") == density
            assert page.theme_selector.currentData() == theme
            assert page.search.text() == "JUANIS"
            assert page.table is selected_table
            assert page.table.selected_row_id() == _THEME_ID
            assert presenter.mock_calls == calls_before_density
            assert page.search.height() >= metrics.input_height
            assert page.new_theme_button.height() >= metrics.button_height
            assert page.table.rowHeight(0) >= metrics.table_row_height
            assert sidebar.active_route == "appearance"
            assert sidebar._search.height() >= metrics.input_height
            assert sidebar._nav.sizeHintForRow(0) >= metrics.sidebar_item_height
            for button in (sidebar._toggle, window.top_bar._notifications_button, window.top_bar._settings_button):
                assert button.width() >= metrics.icon_button_size
                assert button.height() >= metrics.icon_button_size
                assert button.visibleRegion().boundingRect() == button.rect()

            for control in (selector, page.theme_selector):
                assert control.isVisible() and control.isEnabled()
                assert control.height() >= metrics.input_height
                assert control.visibleRegion().boundingRect() == control.rect()
                bounds = QRect(control.mapTo(window, QPoint()), control.size())
                assert window.rect().contains(bounds)
            assert settings.status() == QSettings.NoError
            persisted = QSettings(settings_path, QSettings.IniFormat)
            assert persisted.value("appearance/density") == density
            assert persisted.value("appearance/theme") == theme

            artifacts = Path(os.environ.get("SPJ_UI_VISUAL_ARTIFACTS", str(ui_tmp_path)))
            artifacts.mkdir(parents=True, exist_ok=True)
            capture = window.grab()
            assert not capture.isNull()
            assert capture.save(str(artifacts / f"{theme}-{density}-{size[0]}x{size[1]}-density-settings.png"))
    finally:
        window.close()
        window.deleteLater()
        app.sendPostedEvents(None, QEvent.DeferredDelete)
