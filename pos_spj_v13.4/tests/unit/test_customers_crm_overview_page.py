"""CRM-15 — Dashboard: CustomersCrmOverviewPage + CustomerCrmPresenter.dashboard()."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from decimal import Decimal

import pytest

QtWidgets = pytest.importorskip(
    "PyQt5.QtWidgets", reason="PyQt5 desktop runtime unavailable", exc_type=ImportError)
QApplication = QtWidgets.QApplication

from backend.application.crm.queries.customer_dashboard_query_service import (
    CustomerDashboardView,
    PipelineStageSlice,
)
from frontend.desktop.modules.customers_crm.customers_crm_presenter import CustomerCrmPresenter
from frontend.desktop.modules.customers_crm.pages.overview_page import CustomersCrmOverviewPage


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class _FakeSession:
    def __init__(self, user_id="u1") -> None:
        self.user_id = user_id

    def tiene_permiso(self, _permission: str) -> bool:
        return True


class _FakeDashboardQueryService:
    def __init__(self, view: CustomerDashboardView) -> None:
        self._view = view
        self.calls: list[dict] = []

    def get_dashboard(self, **kwargs) -> CustomerDashboardView:
        self.calls.append(kwargs)
        return self._view


_SAMPLE_VIEW = CustomerDashboardView(
    leads_new_count=3, leads_pending_count=5, opportunities_open_count=7,
    weighted_pipeline=Decimal("12500.50"), overdue_activities_count=2,
    cases_out_of_sla_count=1, total_pipeline=Decimal("40000"),
    pipeline_by_stage=(
        PipelineStageSlice(stage_name="Prospección", amount=Decimal("10000")),
        PipelineStageSlice(stage_name="Propuesta", amount=Decimal("30000")),
    ))


class TestCustomerCrmPresenterDashboard:
    def test_returns_empty_view_when_nothing_wired(self):
        presenter = CustomerCrmPresenter(session_context=_FakeSession())
        view = presenter.dashboard()
        assert view == CustomerDashboardView()

    def test_delegates_to_wired_query_service_with_actor_and_team(self):
        fake_service = _FakeDashboardQueryService(_SAMPLE_VIEW)
        presenter = CustomerCrmPresenter(
            session_context=_FakeSession(user_id="u42"),
            query_services={"dashboard": fake_service},
            team_member_ids=("u42", "u43"))
        view = presenter.dashboard()
        assert view is _SAMPLE_VIEW
        assert fake_service.calls == [{"actor_user_id": "u42", "team_member_ids": ("u42", "u43")}]


class _FakePresenter:
    def __init__(self, view: CustomerDashboardView) -> None:
        self._view = view

    def dashboard(self) -> CustomerDashboardView:
        return self._view


class _RaisingPresenter:
    def dashboard(self):
        raise RuntimeError("boom")


class TestCustomersCrmOverviewPage:
    def test_build_kpis_reflects_dashboard_view(self):
        kpis = CustomersCrmOverviewPage._build_kpis(_SAMPLE_VIEW)
        assert kpis[0].value == "3"
        assert kpis[3].value == "$12,500.50"

    def test_reload_populates_kpi_bar_without_raising(self, app):
        page = CustomersCrmOverviewPage(_FakePresenter(_SAMPLE_VIEW))
        page.reload()
        assert page._loaded is True

    def test_reload_shows_danger_variant_when_overdue(self):
        kpis = CustomersCrmOverviewPage._build_kpis(_SAMPLE_VIEW)
        overdue_kpi = next(k for k in kpis if k.key == "activities_overdue")
        assert overdue_kpi.variant == "danger"

    def test_reload_shows_success_variant_when_nothing_overdue(self):
        clean_view = CustomerDashboardView()
        kpis = CustomersCrmOverviewPage._build_kpis(clean_view)
        overdue_kpi = next(k for k in kpis if k.key == "activities_overdue")
        assert overdue_kpi.variant == "success"

    def test_alerts_built_only_when_counts_positive(self):
        alerts = CustomersCrmOverviewPage._build_alerts(_SAMPLE_VIEW)
        assert len(alerts) == 2
        assert all(variant == "danger" for variant, _msg, _help in alerts)

    def test_no_alerts_when_dashboard_is_clean(self):
        clean_view = CustomerDashboardView()
        assert CustomersCrmOverviewPage._build_alerts(clean_view) == []

    def test_pipeline_chart_uses_stage_names_as_categories(self):
        dto = CustomersCrmOverviewPage._build_pipeline_chart(_SAMPLE_VIEW)
        assert dto.categories == ("Prospección", "Propuesta")
        assert dto.series[0].data == (10000.0, 30000.0)

    def test_pipeline_chart_empty_when_no_stages(self):
        dto = CustomersCrmOverviewPage._build_pipeline_chart(CustomerDashboardView())
        assert dto.is_empty()

    def test_reload_end_to_end_does_not_raise(self, app):
        page = CustomersCrmOverviewPage(_FakePresenter(_SAMPLE_VIEW))
        page.reload()
        assert page._loaded is True
        assert page._status.isHidden()

    def test_reload_shows_error_state_when_presenter_raises(self, app):
        page = CustomersCrmOverviewPage(_RaisingPresenter())
        page.reload()
        assert page._loaded is False
        assert page._status.property("state") == "ERROR"

    def test_ensure_loaded_is_idempotent(self, app):
        presenter = _FakePresenter(_SAMPLE_VIEW)
        page = CustomersCrmOverviewPage(presenter)
        page.ensure_loaded()
        page.ensure_loaded()
        assert page._loaded is True
