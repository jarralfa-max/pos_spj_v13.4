"""ASSET-16 — routes, capability resolver, and AssetsPresenter (no PyQt widgets
instantiated here; see test_assets_ui_pages.py for the widget-level tests)."""

from backend.application.assets.permissions import AssetPermissions
from backend.application.assets.queries.dto import (
    AssetDashboardKPIsDTO,
    AssetSummaryDTO,
)
from backend.domain.assets.enums import AssetCondition, AssetCriticality, AssetStatus
from frontend.desktop.modules.assets.assets_presenter import AssetsPresenter
from frontend.desktop.modules.assets.assets_routes import (
    ASSET_ROUTES,
    grouped_routes,
    visible_routes,
)
from frontend.desktop.modules.assets.capability_resolver import resolve_assets_capabilities
from frontend.desktop.modules.assets.view_models import AssetsCapabilities


class _FakeSession:
    user_id = "u1"
    sucursal_id = "br-1"

    def __init__(self, allowed: set[str] | None = None) -> None:
        self._allowed = allowed

    def tiene_permiso(self, permission: str) -> bool:
        return True if self._allowed is None else permission in self._allowed


class TestAssetRoutes:
    def test_every_route_has_a_declared_capability_field(self):
        caps_fields = set(AssetsCapabilities().__dict__)
        for route in ASSET_ROUTES:
            assert route.capability in caps_fields

    def test_every_route_permission_is_a_known_asset_permission(self):
        from backend.application.assets.permissions import ALL_ASSET_PERMISSIONS
        for route in ASSET_ROUTES:
            assert route.required_permission in ALL_ASSET_PERMISSIONS

    def test_route_ids_are_unique(self):
        ids = [r.route_id for r in ASSET_ROUTES]
        assert len(ids) == len(set(ids))

    def test_no_module_view_hides_everything(self):
        caps = AssetsCapabilities()  # all False
        assert visible_routes(caps) == ()

    def test_full_capabilities_show_every_route(self):
        caps = AssetsCapabilities(**{f: True for f in AssetsCapabilities().__dict__})
        assert len(visible_routes(caps)) == len(ASSET_ROUTES)

    def test_grouped_routes_preserve_declaration_order(self):
        groups = [g for g, _ in grouped_routes()]
        assert groups[0] == "Resumen"
        assert "Mantenimiento" in groups


class TestCapabilityResolver:
    def test_grants_only_permitted_groups(self):
        caps = resolve_assets_capabilities(
            lambda p: p in (AssetPermissions.VIEW, AssetPermissions.DASHBOARD_VIEW))
        assert caps.module_view is True
        assert caps.activos is True
        assert caps.mantenimiento is False


class TestAssetsPresenter:
    def test_dashboard_degrades_to_zeroed_kpis_when_unwired(self):
        presenter = AssetsPresenter(session_context=_FakeSession())
        kpis = presenter.dashboard()
        assert kpis == AssetDashboardKPIsDTO(0, 0, 0, 0, 0)

    def test_dashboard_delegates_to_query_service(self):
        class _FakeDashboard:
            def kpis(self, *, branch_id):
                assert branch_id == "br-1"
                return AssetDashboardKPIsDTO(5, 3, 1, 1, 0)

        presenter = AssetsPresenter(
            session_context=_FakeSession(), query_services={"dashboard": _FakeDashboard()})
        assert presenter.dashboard().total_assets == 5

    def test_directory_empty_when_unwired(self):
        presenter = AssetsPresenter(session_context=_FakeSession())
        assert presenter.directory() == []

    def test_directory_filters_by_search_and_status(self):
        items = [
            AssetSummaryDTO("a1", "ACT-1", "Refrigerador", "Refrigeración", "br-1", None,
                            None, AssetStatus.AVAILABLE, AssetCondition.GOOD,
                            AssetCriticality.MEDIUM),
            AssetSummaryDTO("a2", "ACT-2", "Báscula", "Básculas", "br-1", None, None,
                            AssetStatus.OUT_OF_SERVICE, AssetCondition.FAIR,
                            AssetCriticality.LOW),
        ]

        class _FakeDirectory:
            def list_by_branch(self, branch_id):
                return items

        presenter = AssetsPresenter(
            session_context=_FakeSession(), query_services={"directory": _FakeDirectory()})
        assert [i.id for i in presenter.directory(search="refri")] == ["a1"]
        assert [i.id for i in presenter.directory(status="OUT_OF_SERVICE")] == ["a2"]

    def test_detail_none_when_unwired(self):
        presenter = AssetsPresenter(session_context=_FakeSession())
        assert presenter.detail("a1") is None

    def test_capabilities_reflect_session_permissions(self):
        presenter = AssetsPresenter(
            session_context=_FakeSession(allowed={AssetPermissions.VIEW,
                                                  AssetPermissions.DASHBOARD_VIEW}))
        caps = presenter.capabilities()
        assert caps.activos is True
        assert caps.bajas is False
