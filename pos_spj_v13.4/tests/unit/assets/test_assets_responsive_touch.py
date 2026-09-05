"""ASSET-20 — responsive behavior at the master prompt's named resolutions
(§100) and accessibility metadata (§104) on the Activos workspace.

No dedicated compact/comfortable/touch density *system* exists anywhere in
this repo's Design System yet — same documented gap
``customers_crm_workspace.py`` already flagged for its own module (see
``docs/refactor/ASSET-20_responsive_touch.md``). This phase verifies and
locks in the one real lever that DOES exist: ``PageHeader(compact=...)`` +
the ``SideNav`` width collapse below ``ResponsiveBreakpoints.COMPACT``,
already wired into ``AssetsWorkspace`` since ASSET-16.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

QtWidgets = pytest.importorskip(
    "PyQt5.QtWidgets", reason="PyQt5 desktop runtime unavailable", exc_type=ImportError)
QApplication = QtWidgets.QApplication

from frontend.desktop.modules.assets.assets_presenter import AssetsPresenter
from frontend.desktop.modules.assets.assets_workspace import AssetsWorkspace
from frontend.desktop.themes.tokens import ResponsiveBreakpoints


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class _FakeSession:
    user_id = "u1"
    sucursal_id = "br-1"

    def tiene_permiso(self, _permission: str) -> bool:
        return True


_NAMED_RESOLUTIONS = [(1366, 768), (1440, 900), (1600, 900), (1920, 1080)]


class TestAssetsWorkspaceResponsive:
    @pytest.mark.parametrize("width,height", _NAMED_RESOLUTIONS)
    def test_renders_without_error_at_named_resolution(self, app, width, height):
        presenter = AssetsPresenter(session_context=_FakeSession())
        workspace = AssetsWorkspace(presenter)
        workspace.resize(width, height)
        # None of §100's named resolutions are below the COMPACT breakpoint
        # (1366px) under the current shared threshold — every one renders
        # the full-width nav, same behavior `customers_crm` already has at
        # these sizes. Assert that explicitly rather than assuming it.
        assert width >= ResponsiveBreakpoints.COMPACT
        assert workspace._nav.maximumWidth() == 240

    def test_collapses_nav_below_compact_breakpoint(self, app):
        presenter = AssetsPresenter(session_context=_FakeSession())
        workspace = AssetsWorkspace(presenter)
        workspace.resize(1200, 800)
        workspace.resizeEvent(None)
        assert workspace._nav.maximumWidth() == 180
        assert workspace._nav.minimumWidth() == 160

    def test_full_width_nav_above_compact_breakpoint(self, app):
        presenter = AssetsPresenter(session_context=_FakeSession())
        workspace = AssetsWorkspace(presenter)
        workspace.resize(1920, 1080)
        workspace.resizeEvent(None)
        assert workspace._nav.maximumWidth() == 240
        assert workspace._nav.minimumWidth() == 180


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
