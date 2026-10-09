"""Activos uses the Pricing module layout and preserves manual sidebar choice.

The module header spans the sidebar and viewport at all supported resolutions;
resizing does not replace the user's expanded/collapsed navigation preference.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

QtWidgets = pytest.importorskip(
    "PyQt5.QtWidgets", reason="PyQt5 desktop runtime unavailable", exc_type=ImportError)
QApplication = QtWidgets.QApplication

from frontend.desktop.modules.assets.assets_presenter import AssetsPresenter
from frontend.desktop.modules.assets.assets_workspace import AssetsWorkspace


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class _FakeSession:
    user_id = "u1"
    sucursal_id = "br-1"

    def tiene_permiso(self, _permission: str) -> bool:
        return True


_NAMED_RESOLUTIONS = [(1280, 720), (1366, 768), (1440, 900), (1600, 900), (1920, 1080)]


class TestAssetsWorkspaceResponsive:
    @pytest.mark.parametrize("width,height", _NAMED_RESOLUTIONS)
    def test_renders_without_error_at_named_resolution(self, app, width, height):
        presenter = AssetsPresenter(session_context=_FakeSession())
        workspace = AssetsWorkspace(presenter)
        workspace.resize(width, height)
        workspace.show()
        app.processEvents()
        assert workspace._nav.maximumWidth() == 240
        assert workspace._nav.minimumWidth() == 180
        assert workspace._header is workspace.module_layout.header
        assert workspace._header.x() == 20
        assert workspace._header.width() == width - 40
        assert workspace._header.geometry().bottom() < workspace._nav.y()
        workspace.close()

    def test_resize_preserves_manually_collapsed_nav_and_active_page(self, app):
        presenter = AssetsPresenter(session_context=_FakeSession())
        workspace = AssetsWorkspace(presenter)
        workspace.select_route("assets.directory")
        active_page = workspace._stack.currentWidget()
        workspace._nav.set_collapsed(True)
        workspace.show()
        for width, height in _NAMED_RESOLUTIONS:
            workspace.resize(width, height)
            app.processEvents()
            assert workspace._nav.maximumWidth() == 64
            assert workspace._nav.minimumWidth() == 60
            assert workspace._stack.currentWidget() is active_page
        workspace.close()

    def test_resize_preserves_manually_expanded_nav(self, app):
        presenter = AssetsPresenter(session_context=_FakeSession())
        workspace = AssetsWorkspace(presenter)
        workspace._nav.set_collapsed(True)
        workspace._nav.set_collapsed(False)
        workspace.show()
        for width, height in reversed(_NAMED_RESOLUTIONS):
            workspace.resize(width, height)
            app.processEvents()
            assert workspace._nav.maximumWidth() == 240
            assert workspace._nav.minimumWidth() == 180
        workspace.close()


class TestAssetsWorkspaceAccessibility:
    def test_key_widgets_have_accessible_names(self, app):
        presenter = AssetsPresenter(session_context=_FakeSession())
        workspace = AssetsWorkspace(presenter)
        assert workspace.accessibleName()
        assert workspace._nav.accessibleName()
        assert workspace._stack.accessibleName()

    def test_directory_page_inputs_have_accessible_names(self, app):
        from frontend.desktop.modules.assets.pages.assets_directory_page import (
            AssetsDirectoryPage,
        )
        presenter = AssetsPresenter(session_context=_FakeSession())
        page = AssetsDirectoryPage(presenter)
        assert page._search.accessibleName()
        assert page._table.accessibleName()
