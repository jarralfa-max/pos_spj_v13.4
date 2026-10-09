"""Protect module geometry and navigation while using neutral business pages."""

import os
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QLineEdit, QPushButton, QScrollArea

from frontend.desktop.components.view_states import ViewState
from tests.ui.test_route_sidebar_icons import workspace_case  # noqa: F401


def _assert_layout(workspace):
    layout = workspace.module_layout
    header, nav, viewport = layout.header, workspace._nav, layout.viewport
    assert workspace._header is header
    assert header.parentWidget() is workspace
    assert nav.parentWidget() is workspace
    assert viewport.page() is workspace._stack
    assert (header.x(), header.y(), header.width()) == (20, 16, workspace.width() - 40)
    assert header.geometry().bottom() < nav.y()
    assert nav.x() == 20
    assert viewport.x() == nav.x() + nav.width() + 16
    assert viewport.y() == nav.y()
    assert viewport.height() == nav.height()
    assert viewport.x() + viewport.width() == workspace.width() - 20
    assert viewport.y() + viewport.height() == workspace.height() - 16
    assert not viewport.isAncestorOf(header)
    assert not viewport.isAncestorOf(nav)
    assert viewport.verticalScrollBar().maximum() == 0
    if hasattr(workspace, "_status_bar"):
        context = workspace._status_bar
        assert header.geometry().bottom() < context.y()
        assert context.geometry().bottom() < nav.y()
        assert (context.x(), context.width()) == (20, header.width())


def test_route_module_layout_preserves_state_through_resize_theme_and_collapse(workspace_case):
    case = workspace_case
    workspace = case.workspace
    workspace.select_route(getattr(case.routes[-1], case.key))
    active = workspace._stack.currentWidget()
    page = active.findChild(QScrollArea).widget()
    editor = QLineEdit(page)
    editor.setText("Captura pendiente")
    workspace.show()

    for theme in ("light", "dark"):
        for density in ("compact", "comfortable", "touch"):
            case.manager.apply(case.app, theme, density=density)
            for collapsed in (False, True):
                workspace._nav.set_collapsed(collapsed)
                for width, height in ((1280, 720), (1366, 768), (1440, 900), (1600, 900), (1920, 1080)):
                    workspace.resize(width, height)
                    case.app.processEvents()
                    _assert_layout(workspace)
                    assert workspace._nav.width() == (64 if collapsed else 240)
                    assert workspace._nav.collapsed is collapsed
                    assert workspace._stack.currentWidget() is active
                    assert editor.text() == "Captura pendiente"
                    artifacts = os.environ.get("SPJ_MODULE_LAYOUT_ARTIFACTS")
                    if artifacts and width == 1366 and not collapsed and density != "compact":
                        directory = Path(artifacts)
                        directory.mkdir(parents=True, exist_ok=True)
                        destination = directory / f"{workspace.objectName()}-{theme}-{density}-{width}x{height}.png"
                        assert workspace.grab().save(str(destination))
    if hasattr(workspace, "_status_bar"):
        refreshed = []
        page.refresh = lambda: refreshed.append(page)
        refresh = next(button for button in workspace._header.findChildren(QPushButton)
                       if button.text() == "Actualizar")
        QTest.mouseClick(refresh, Qt.LeftButton)
        assert refreshed == [page]
        assert workspace._stack.currentWidget() is active


def test_denied_module_keeps_header_sidebar_and_single_permission_state(workspace_case):
    case = workspace_case
    workspace = case.workspace
    case.capabilities.module_view = False
    workspace.refresh_permissions()
    workspace.resize(1280, 720)
    workspace.show()
    case.app.processEvents()
    _assert_layout(workspace)
    assert workspace._stack.count() == 1
    assert workspace._stack.currentWidget().property("state") == ViewState.NO_PERMISSION
    assert workspace._nav.count() == 1
    assert workspace._nav.item(0).data(Qt.UserRole) is None
