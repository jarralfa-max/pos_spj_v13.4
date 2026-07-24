from backend.application.transfers.permissions import TransferPermissions
from backend.application.transfers.queries.navigation_query_service import (
    TransferNavigationBadges,
    TransferNavigationQueryService,
)
from frontend.desktop.modules.transfers.navigation.transfers_sidebar import (
    TRANSFERS_NAV,
    visible_entries,
)
from frontend.desktop.modules.transfers.transfers_routes import TRANSFERS_ROUTE_IDS, build_page


class _BadgeReadPort:
    def navigation_badges(self, *, user_id, branch_id):
        assert user_id == "user" and branch_id == "branch"
        return TransferNavigationBadges(pending_requests=3, open_differences=2)


def test_transfers_sidebar_is_canonical_and_permission_filtered_with_query_badges():
    assert [entry.title for entry in TRANSFERS_NAV] == [
        "Resumen", "Solicitudes", "Aprobaciones", "Picking", "Listas para despacho",
        "En tránsito", "Recepciones", "Diferencias", "Devoluciones", "Sugerencias",
        "Trazabilidad", "Alertas", "Análisis", "Auditoría", "Configuración",
    ]
    badges = TransferNavigationQueryService(_BadgeReadPort()).get_badges(user_id="user", branch_id="branch").as_dict()
    visible = visible_entries(lambda code: code in {TransferPermissions.DASHBOARD_VIEW, TransferPermissions.REQUEST_VIEW}, badges)
    assert [(entry.page_id, badge) for entry, badge in visible] == [
        ("transfers_overview", None), ("transfers_requests", 3),
        ("transfers_suggestions", None), ("transfers_alerts", None),
    ]


def test_transfers_routes_are_single_canonical_sidebar_routes():
    assert TRANSFERS_ROUTE_IDS == {entry.page_id for entry in TRANSFERS_NAV}
    try:
        build_page("legacy_transferencias", presenter=None)
    except KeyError:
        pass
    else:
        raise AssertionError("Legacy route must not be accepted")
