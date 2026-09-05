"""ASSET-19 — Maintenance UI: presenter.work_orders(), WorkOrdersBoardPage,
MaintenanceAgendaPage. Both pages are explicitly READ-ONLY previews — no
drag/drop or status-changing action exists (no use case to call yet)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

QtWidgets = pytest.importorskip(
    "PyQt5.QtWidgets", reason="PyQt5 desktop runtime unavailable", exc_type=ImportError)
QApplication = QtWidgets.QApplication

from backend.application.assets.queries.dto import MaintenanceWorkOrderSummaryDTO
from backend.domain.assets.enums import AssetCriticality
from frontend.desktop.modules.assets.assets_presenter import AssetsPresenter
from frontend.desktop.modules.assets.pages.maintenance_agenda_page import MaintenanceAgendaPage
from frontend.desktop.modules.assets.pages.work_orders_board_page import WorkOrdersBoardPage


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class _FakeSession:
    user_id = "u1"
    sucursal_id = "br-1"

    def tiene_permiso(self, _permission: str) -> bool:
        return True


def _wo(wo_id, status, scheduled_at=None):
    return MaintenanceWorkOrderSummaryDTO(
        id=wo_id, work_order_number=f"WO-{wo_id}", asset_id="asset-1", status=status,
        priority=AssetCriticality.MEDIUM, scheduled_at=scheduled_at)


class TestAssetsPresenterWorkOrders:
    def test_work_orders_empty_when_unwired(self):
        presenter = AssetsPresenter(session_context=_FakeSession())
        assert presenter.work_orders() == []

    def test_work_orders_delegates_to_query_service(self):
        class _FakeWOService:
            def list_all_open(self, *, branch_id):
                assert branch_id == "br-1"
                return [_wo("1", "REQUESTED")]

        presenter = AssetsPresenter(
            session_context=_FakeSession(), query_services={"work_orders": _FakeWOService()})
        results = presenter.work_orders()
        assert len(results) == 1
        assert results[0].id == "1"


class TestWorkOrdersBoardPage:
    def test_reload_groups_by_status(self, app):
        class _FakeWOService:
            def list_all_open(self, *, branch_id):
                return [_wo("1", "REQUESTED"), _wo("2", "IN_PROGRESS"), _wo("3", "REQUESTED")]

        presenter = AssetsPresenter(
            session_context=_FakeSession(), query_services={"work_orders": _FakeWOService()})
        page = WorkOrdersBoardPage(presenter)
        page.reload()
        assert page._loaded is True
        from backend.domain.assets.enums import MaintenanceWorkOrderStatus
        requested_column = page._columns[MaintenanceWorkOrderStatus.REQUESTED]
        assert requested_column._cards_layout.count() == 2

    def test_reload_shows_empty_state(self, app):
        class _EmptyWOService:
            def list_all_open(self, *, branch_id):
                return []

        presenter = AssetsPresenter(
            session_context=_FakeSession(), query_services={"work_orders": _EmptyWOService()})
        page = WorkOrdersBoardPage(presenter)
        page.reload()
        assert not page._empty.isHidden()

    def test_reload_shows_error_state_on_exception(self, app):
        class _BrokenWOService:
            def list_all_open(self, *, branch_id):
                raise RuntimeError("boom")

        presenter = AssetsPresenter(
            session_context=_FakeSession(), query_services={"work_orders": _BrokenWOService()})
        page = WorkOrdersBoardPage(presenter)
        page.reload()
        assert page._loaded is False
        assert not page._status.isHidden()


class TestMaintenanceAgendaPage:
    def test_reload_sorts_by_scheduled_date(self, app):
        class _FakeWOService:
            def list_all_open(self, *, branch_id):
                return [
                    _wo("1", "SCHEDULED", scheduled_at="2026-09-20"),
                    _wo("2", "SCHEDULED", scheduled_at="2026-09-05"),
                    _wo("3", "REQUESTED", scheduled_at=None),
                ]

        presenter = AssetsPresenter(
            session_context=_FakeSession(), query_services={"work_orders": _FakeWOService()})
        page = MaintenanceAgendaPage(presenter)
        page.reload()
        assert page._table.rowCount() == 2  # unscheduled WO-3 excluded
        assert page._table.item(0, 0).text() == "WO-2"  # earlier date first

    def test_reload_shows_empty_state_when_nothing_scheduled(self, app):
        class _EmptyWOService:
            def list_all_open(self, *, branch_id):
                return []

        presenter = AssetsPresenter(
            session_context=_FakeSession(), query_services={"work_orders": _EmptyWOService()})
        page = MaintenanceAgendaPage(presenter)
        page.reload()
        assert not page._empty.isHidden()
        assert page._table.isHidden()
