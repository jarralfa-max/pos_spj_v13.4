"""Render the real shell and gallery at every required desktop size.

These are geometry/interaction assertions plus reviewable PNG evidence. Pixel
baseline comparison is intentionally not claimed without an approved baseline.
"""
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
from PyQt5.QtCore import QEvent, QPoint, QRect, QSettings
from PyQt5.QtGui import QFontDatabase
from PyQt5.QtWidgets import QApplication, QPushButton

from frontend.desktop.components.page_viewport import PageViewport
from frontend.desktop.design_system.component_gallery import build_gallery
from frontend.desktop.shell.application_shell.application_window import ApplicationWindow
from frontend.desktop.shell.application_shell.notification_drawer import NotificationItem
from frontend.desktop.shell.router.desktop_router import DesktopRouter
from frontend.desktop.shell.routing.route_definition import RouteDefinition
from frontend.desktop.shell.routing.route_registry import RouteRegistry
from frontend.desktop.shell.routing.view_factory_registry import ViewFactoryRegistry
from frontend.desktop.shell.sidebar.global_sidebar import GlobalSidebar
from frontend.desktop.shell.sidebar.sidebar_item_view_model import SidebarItemViewModel
from frontend.desktop.themes.tokens import ResponsiveBreakpoints
from tests.ui.shell.conftest import make_context


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def settle(app):
    for _ in range(4):
        app.processEvents()


def save(window, directory, name):
    directory.mkdir(parents=True, exist_ok=True)
    screenshot = window.grab()
    assert not screenshot.isNull()
    assert screenshot.save(str(directory / f"{name}.png"))


@pytest.mark.parametrize("size", ResponsiveBreakpoints.VALIDATION_SIZES)
@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("density", ["comfortable", "touch"])
def test_shell_gallery_controls_remain_reachable(app, ui_tmp_path, size, theme, density):
    assert QFontDatabase().families(), "Visual evidence requires real fonts"
    gallery = build_gallery(theme, density)
    registry = RouteRegistry()
    registry.register(RouteDefinition(route_id="gallery", module_id="gallery",
                                      title="Componentes JUANIS", view_factory_id="gallery"))
    factories = ViewFactoryRegistry()
    factories.register("gallery", lambda: gallery)
    router = DesktopRouter(route_registry=registry, view_factory_registry=factories,
                           initial_context=make_context())
    settings = QSettings(str(ui_tmp_path / "navigation.ini"), QSettings.IniFormat)
    sidebar = GlobalSidebar(settings=settings, settings_key="visual")
    sidebar.set_items((SidebarItemViewModel("gallery", "gallery", "Componentes", "settings", "", 0, None, True),))
    window = ApplicationWindow(router=router, sidebar=sidebar)
    window.navigate("gallery")
    window.show()
    # Resize after show to emulate each viewport independently of the actual
    # offscreen plugin's synthetic monitor; dialog screen bounds have own tests.
    window.resize(*size)
    settle(app)
    assert (window.width(), window.height()) == size
    for button in window.top_bar.findChildren(QPushButton):
        if button.isVisible():
            assert window.rect().contains(QRect(button.mapTo(window, QPoint()), button.size())), button.accessibleName()
    viewport = gallery.findChild(PageViewport)
    assert viewport is not None and viewport.verticalScrollBar().maximum() > 0
    artifacts = Path(os.environ.get("SPJ_UI_VISUAL_ARTIFACTS", str(ui_tmp_path)))
    label = f"{theme}-{density}-{size[0]}x{size[1]}"
    save(window, artifacts, label + "-expanded")

    sidebar.set_collapsed(True)
    window.notification_drawer.add_notification(NotificationItem(
        "sample", "Recepción pendiente", "Revise la recepción de mercancía.", datetime.now(timezone.utc)))
    window.notification_drawer.open()
    settle(app)
    assert 60 <= sidebar.width() <= 64
    assert window.rect().contains(QRect(sidebar._toggle.mapTo(window, QPoint()), sidebar._toggle.size()))
    assert window.rect().contains(QRect(window.notification_drawer.mapTo(window, QPoint()), window.notification_drawer.size()))
    save(window, artifacts, label + "-collapsed-notifications")
    window.notification_drawer.close()
    viewport.verticalScrollBar().setValue(viewport.verticalScrollBar().maximum())
    settle(app)
    assert viewport.verticalScrollBar().value() == viewport.verticalScrollBar().maximum()
    save(window, artifacts, label + "-scrolled")
    window.close()
    window.deleteLater()
    app.sendPostedEvents(None, QEvent.DeferredDelete)
