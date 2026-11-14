"""SDLC-BI-001: BI respeta la sucursal del usuario y no concede nada por omisión.

Antes las rutas recibían `branch_id` y lo tiraban, los presenters consultaban con
`DashboardFilters()` vacío y `BiDashboardService` permitía todo si nadie le pasaba
verificador: cualquiera con acceso al módulo veía las cifras de toda la empresa.
"""
from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from backend.application.analytics.access import BiAccess, build_bi_access  # noqa: E402
from backend.application.analytics.dto.bi_dashboard_dto import DashboardFilters  # noqa: E402
from backend.application.analytics.permissions import AnalyticsPermissions  # noqa: E402
from backend.application.analytics.queries.bi_dashboard_query_service import (  # noqa: E402
    BiDashboardQueryService,
)
from backend.application.analytics.services.bi_dashboard_service import (  # noqa: E402
    BiDashboardService,
)
from backend.domain.analytics.exceptions import AnalyticsPermissionDeniedError  # noqa: E402
from backend.shared.ids import new_uuid  # noqa: E402
from frontend.desktop.modules.business_intelligence.presenters.analytical_section_presenter import (  # noqa: E402
    AnalyticalSectionPresenter,
)
from frontend.desktop.modules.business_intelligence.presenters.executive_dashboard_presenter import (  # noqa: E402
    ExecutiveDashboardPresenter,
)
from frontend.desktop.modules.business_intelligence.presenters.forecast_explorer_presenter import (  # noqa: E402
    ForecastExplorerPresenter,
    ForecastUnavailableError,
)
from frontend.desktop.modules.business_intelligence.presenters.reports_presenter import (  # noqa: E402
    ReportsPresenter,
)
from tests.integration import bi_seed as S  # noqa: E402


@pytest.fixture(scope="module")
def mundo():
    conn = S.fresh_db()
    centro, norte = S.add_branch(conn, "Centro"), S.add_branch(conn, "Norte")
    pollo = new_uuid()      # `bi_seed.add_product` escribe en `productos`, ya retirada
    S.add_sale(conn, centro, [(pollo, 1, 100.0, 10.0)], when=S.this_month_day())
    S.add_sale(conn, norte, [(pollo, 1, 900.0, 10.0)], when=S.this_month_day())
    conn.commit()
    return SimpleNamespace(conn=conn, centro=centro, norte=norte)


def _acceso(mundo, *, permitidas=None, sesion=None) -> BiAccess:
    return BiAccess(can=lambda _codigo: True,
                    allowed_branch_ids=(mundo.centro,) if permitidas is None else permitidas,
                    default_branch_id=mundo.centro if sesion is None else sesion)


def _ventas(kpis) -> float:
    return next(float(k["value"]) for k in kpis if k["key"] == "ventas_netas")


def _servicio(mundo, acceso) -> BiDashboardService:
    return BiDashboardService(BiDashboardQueryService(mundo.conn), permission_checker=acceso.can,
                              branch_scope=acceso.scope)


# ── servicio ────────────────────────────────────────────────────────────────
def test_the_service_grants_nothing_by_default(mundo):
    servicio = BiDashboardService(BiDashboardQueryService(mundo.conn))
    with pytest.raises(AnalyticsPermissionDeniedError):
        servicio.build_dashboard(DashboardFilters())
    with pytest.raises(AnalyticsPermissionDeniedError):
        servicio.section_data("ventas", DashboardFilters())


def test_no_branch_filter_means_the_users_branch_not_the_whole_company(mundo):
    payload = _servicio(mundo, _acceso(mundo)).build_dashboard(DashboardFilters())
    assert payload.filters["branch_id"] == mundo.centro
    assert _ventas(payload.kpis) == pytest.approx(100.0)


def test_another_branch_is_refused(mundo):
    with pytest.raises(AnalyticsPermissionDeniedError):
        _servicio(mundo, _acceso(mundo)).build_dashboard(DashboardFilters(branch_id=mundo.norte))


def test_a_company_wide_user_can_see_everything_or_one_branch(mundo):
    servicio = _servicio(mundo, BiAccess(can=lambda _c: True, allowed_branch_ids=None))
    assert _ventas(servicio.build_dashboard(DashboardFilters()).kpis) == pytest.approx(1000.0)
    uno = servicio.build_dashboard(DashboardFilters(branch_id=mundo.norte))
    assert _ventas(uno.kpis) == pytest.approx(900.0)


def test_a_section_without_permission_returns_nothing(mundo):
    acceso = BiAccess(can=lambda _c: False, allowed_branch_ids=None)
    with pytest.raises(AnalyticsPermissionDeniedError):
        _servicio(mundo, acceso).section_data("finanzas", DashboardFilters())


def test_a_user_with_no_branch_sees_nothing(mundo):
    acceso = BiAccess(can=lambda _c: True, allowed_branch_ids=())
    with pytest.raises(AnalyticsPermissionDeniedError):
        _servicio(mundo, acceso).build_dashboard(DashboardFilters())


# ── presenters ──────────────────────────────────────────────────────────────
def test_the_executive_presenter_is_scoped_and_can_change_branch_and_dates(mundo):
    acceso = _acceso(mundo, permitidas=(mundo.centro, mundo.norte))
    presenter = ExecutiveDashboardPresenter(mundo.conn, access=acceso)
    assert presenter.kpi_cards()[0].value != ""
    assert presenter.filters.current.branch_id == mundo.centro
    assert presenter.filters.allows_all_branches is False
    assert {b for b, _n in presenter.filters.branch_options()} == {mundo.centro, mundo.norte}

    presenter.filters.set(branch_id=mundo.norte, preset="custom", date_from="2020-01-01",
                          date_to="2020-01-31")

    filtros = presenter.filters.current
    assert filtros.branch_id == mundo.norte
    assert (filtros.date_from, filtros.date_to) == ("2020-01-01", "2020-01-31")


def test_the_filter_cannot_pick_a_branch_outside_the_scope(mundo):
    presenter = ExecutiveDashboardPresenter(mundo.conn, access=_acceso(mundo))
    with pytest.raises(AnalyticsPermissionDeniedError):
        presenter.filters.set(branch_id=mundo.norte)


def test_the_section_presenter_only_sees_the_scoped_branch(mundo):
    presenter = AnalyticalSectionPresenter(mundo.conn, "ventas", access=_acceso(mundo))
    presenter.kpi_cards()
    assert presenter.filters.current.branch_id == mundo.centro


def test_a_report_says_which_branch_it_covers(mundo, tmp_path):
    presenter = ReportsPresenter(mundo.conn, actor_user_id=new_uuid(), access=_acceso(mundo))
    capturado = {}
    presenter._export = SimpleNamespace(export_summary=lambda payload, meta, path, fmt: (
        capturado.update(payload=payload, meta=meta) or path))

    presenter.generate(report_key="executive_summary", fmt="csv",
                       filepath=str(tmp_path / "r.csv"))

    assert capturado["payload"]["filters"]["branch_id"] == mundo.centro
    assert capturado["meta"]["sucursal"] == "Centro"


def test_branch_searches_only_offer_the_scope(mundo):
    presenter = ForecastExplorerPresenter(mundo.conn, access=_acceso(mundo))
    assert [o.id for o in presenter.search_branches("")] == [mundo.centro]


def test_a_forecast_cannot_target_another_branch(mundo):
    presenter = ForecastExplorerPresenter(mundo.conn, access=_acceso(mundo))
    with pytest.raises(ForecastUnavailableError):
        presenter.forecast(product_id=new_uuid(), branch_id=mundo.norte, horizon_days=7)


# ── alcance real de la sesión ───────────────────────────────────────────────
def _usuario(conn, sucursal: str, rol: str = "cajero") -> str:
    uid = new_uuid()
    conn.execute(
        "INSERT INTO usuarios (id, nombre, usuario, password_hash, rol, sucursal_id, activo)"
        " VALUES (?,?,?,?,?,?,1)", (uid, "Ana", f"ana-{uid[-6:]}", "x", rol, sucursal))
    conn.commit()
    return uid


def _sesion(user_id, sucursal, permisos=()):
    return SimpleNamespace(user_id=user_id, active_branch_id=sucursal,
                           tiene_permiso=lambda codigo: codigo in permisos)


def test_a_session_is_limited_to_its_own_branch_by_the_standard_scope(mundo):
    uid = _usuario(mundo.conn, mundo.centro)
    acceso = build_bi_access(mundo.conn, _sesion(uid, mundo.centro))
    assert acceso.allowed_branch_ids == (mundo.centro,)


def test_a_session_keeps_the_site_of_the_station_even_outside_its_assignments(mundo):
    uid = _usuario(mundo.conn, mundo.centro)
    acceso = build_bi_access(mundo.conn, _sesion(uid, mundo.norte))
    assert set(acceso.allowed_branch_ids) == {mundo.centro, mundo.norte}
    assert acceso.default_branch_id == mundo.norte


def test_without_a_session_nothing_is_granted(mundo):
    acceso = build_bi_access(mundo.conn, None)
    assert acceso.allowed_branch_ids == ()
    assert not acceso.can(AnalyticsPermissions.SALES_VIEW)


def test_the_granular_code_of_the_menu_opens_its_section(mundo):
    """El menú pide `INTELIGENCIA_BI.ventas.ver`; el tablero, el código plano. Quien
    ve la entrada debe ver su contenido."""
    uid = _usuario(mundo.conn, mundo.centro)
    acceso = build_bi_access(
        mundo.conn, _sesion(uid, mundo.centro, permisos=(AnalyticsPermissions.SALES_VIEW,)))
    assert acceso.can("INTELIGENCIA_BI.ver_ventas")
    assert not acceso.can("INTELIGENCIA_BI.ver_finanzas")
