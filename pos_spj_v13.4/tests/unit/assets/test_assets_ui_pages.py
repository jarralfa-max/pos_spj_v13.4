"""ASSET-17/18 — widget-level tests for the Activos dashboard, directory and
detail pages, plus the workspace shell that hosts them.

Mirrors ``tests/unit/test_customers_crm_directory_pages.py``'s offscreen-Qt
convention.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

QtWidgets = pytest.importorskip(
    "PyQt5.QtWidgets", reason="PyQt5 desktop runtime unavailable", exc_type=ImportError)
QApplication = QtWidgets.QApplication

from backend.application.assets.queries.dto import AssetDashboardKPIsDTO, AssetDetailDTO, AssetSummaryDTO
from backend.domain.assets.enums import AssetCondition, AssetCriticality, AssetStatus
from frontend.desktop.modules.assets.assets_presenter import AssetsPresenter
from frontend.desktop.modules.assets.assets_workspace import AssetsWorkspace
from frontend.desktop.modules.assets.pages.asset_detail_page import AssetDetailPage
from frontend.desktop.modules.assets.pages.assets_directory_page import AssetsDirectoryPage
from frontend.desktop.modules.assets.pages.overview_page import AssetsOverviewPage


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class _FakeSession:
    user_id = "u1"
    sucursal_id = "br-1"

    def tiene_permiso(self, _permission: str) -> bool:
        return True


def _asset_summary(asset_id="a1", name="Refrigerador", status=AssetStatus.AVAILABLE):
    return AssetSummaryDTO(asset_id, "ACT-000001", name, "Refrigeración", "br-1",
                           "Cocina", None, status, AssetCondition.GOOD, AssetCriticality.MEDIUM)


class TestAssetsOverviewPage:
    def test_reload_renders_kpis_from_presenter(self, app):
        class _FakeDashboard:
            def kpis(self, *, branch_id):
                return AssetDashboardKPIsDTO(10, 6, 2, 1, 1)

        presenter = AssetsPresenter(
            session_context=_FakeSession(), query_services={"dashboard": _FakeDashboard()})
        page = AssetsOverviewPage(presenter)
        page.reload()
        assert page._loaded is True

    def test_reload_shows_error_state_on_exception(self, app):
        class _BrokenDashboard:
            def kpis(self, *, branch_id):
                raise RuntimeError("boom")

        presenter = AssetsPresenter(
            session_context=_FakeSession(), query_services={"dashboard": _BrokenDashboard()})
        page = AssetsOverviewPage(presenter)
        page.reload()
        assert page._loaded is False
        assert not page._status.isHidden()


class TestAssetsDirectoryPage:
    def test_reload_populates_table(self, app):
        class _FakeDirectory:
            def list_by_branch(self, branch_id):
                return [_asset_summary()]

        presenter = AssetsPresenter(
            session_context=_FakeSession(), query_services={"directory": _FakeDirectory()})
        page = AssetsDirectoryPage(presenter)
        page.reload()
        assert page._loaded is True
        assert page._stack.currentWidget() is page._table

    def test_reload_shows_empty_state_when_no_results(self, app):
        class _EmptyDirectory:
            def list_by_branch(self, branch_id):
                return []

        presenter = AssetsPresenter(
            session_context=_FakeSession(), query_services={"directory": _EmptyDirectory()})
        page = AssetsDirectoryPage(presenter)
        page.reload()
        assert page._stack.currentWidget() is page._empty

    def test_double_click_emits_entity_selected(self, app, qtbot=None):
        class _FakeDirectory:
            def list_by_branch(self, branch_id):
                return [_asset_summary(asset_id="a42")]

        presenter = AssetsPresenter(
            session_context=_FakeSession(), query_services={"directory": _FakeDirectory()})
        page = AssetsDirectoryPage(presenter)
        page.reload()
        received = []
        page.entity_selected.connect(received.append)
        page._table.selectRow(0)
        page._on_row_activated(None)
        assert received == ["a42"]


class TestAssetDetailPage:
    def test_show_asset_renders_detail(self, app):
        class _FakeDetail:
            def get(self, asset_id):
                return AssetDetailDTO(
                    asset=_asset_summary(asset_id=asset_id), description="",
                    manufacturer="Marca X", model="M-100", serial_number="SN-1",
                    has_active_assignment=True)

        presenter = AssetsPresenter(
            session_context=_FakeSession(), query_services={"detail": _FakeDetail()})
        page = AssetDetailPage(presenter)
        page.show_asset("a1")
        assert page._labels["manufacturer"].text() == "Marca X"
        assert not page._card.isHidden()

    def test_no_asset_selected_shows_empty_state(self, app):
        presenter = AssetsPresenter(session_context=_FakeSession())
        page = AssetDetailPage(presenter)
        page.reload()
        assert not page._empty.isHidden()

    def test_unknown_asset_shows_empty_state(self, app):
        class _FakeDetail:
            def get(self, asset_id):
                return None

        presenter = AssetsPresenter(
            session_context=_FakeSession(), query_services={"detail": _FakeDetail()})
        page = AssetDetailPage(presenter)
        page.show_asset("missing")
        assert not page._empty.isHidden()


class TestAssetsWorkspace:
    def test_builds_all_routes_and_navigates(self, app):
        presenter = AssetsPresenter(session_context=_FakeSession())
        workspace = AssetsWorkspace(presenter)
        assert len(workspace._route_index_by_id) > 30
        workspace.select_route("assets.directory")
        workspace.select_route("assets.overview")

    def test_directory_selection_opens_detail(self, app):
        class _FakeDirectory:
            def list_by_branch(self, branch_id):
                return [_asset_summary(asset_id="a7")]

        class _FakeDetail:
            def get(self, asset_id):
                return AssetDetailDTO(
                    asset=_asset_summary(asset_id=asset_id), description="",
                    manufacturer="", model="", serial_number=None,
                    has_active_assignment=False)

        presenter = AssetsPresenter(
            session_context=_FakeSession(),
            query_services={"directory": _FakeDirectory(), "detail": _FakeDetail()})
        workspace = AssetsWorkspace(presenter)
        workspace.select_route("assets.directory")
        workspace._open_asset_detail("a7")
        assert workspace._detail_page._asset_id == "a7"

    def test_no_module_view_shows_no_permission_state(self, app):
        class _DenySession:
            user_id = "u2"
            sucursal_id = "br-1"

            def tiene_permiso(self, _permission: str) -> bool:
                return False

        presenter = AssetsPresenter(session_context=_DenySession())
        workspace = AssetsWorkspace(presenter)
        assert workspace._route_index_by_id == {}
