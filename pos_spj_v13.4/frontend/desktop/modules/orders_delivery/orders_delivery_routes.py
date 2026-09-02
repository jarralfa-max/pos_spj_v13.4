"""Single route registry for every internal Pedidos y Delivery page.
Started (ORD-4) mirroring `frontend/desktop/modules/losses/losses_routes.py`
exactly — every route resolved to the same placeholder. ORD-28 wires the
first REAL pages (Resumen/Todos los pedidos/Análisis) behind an optional
`connection`; the remaining ~20 routes stay placeholders, an honest,
documented gap (see docs/refactor/ORD-28_ui_ux.md), not a silent one.
"""

from __future__ import annotations

from frontend.desktop.modules.orders_delivery.navigation.orders_delivery_sidebar import (
    ORDERS_DELIVERY_NAV,
)

ORDERS_DELIVERY_ROUTES = {entry.page_id: entry for entry in ORDERS_DELIVERY_NAV}

# Routes with a REAL page behind them once a `connection` is supplied.
_REAL_ROUTE_BUILDERS: dict[str, str] = {
    "orders_overview": "_build_overview",
    "orders_all": "_build_orders_list",
    "orders_analytics": "_build_analytics",
}


def build_page(page_id: str, connection=None, *, branch_id: str | None = None,
                actor_user_id: str | None = None):
    try:
        entry = ORDERS_DELIVERY_ROUTES[page_id]
    except KeyError as exc:
        raise KeyError(f"Unknown Orders/Delivery route: {page_id}") from exc

    builder_name = _REAL_ROUTE_BUILDERS.get(page_id)
    if connection is not None and branch_id is not None and builder_name is not None:
        return globals()[builder_name](connection, branch_id=branch_id, actor_user_id=actor_user_id)

    from frontend.desktop.modules.orders_delivery.pages import OrdersDeliveryPlaceholderPage
    return OrdersDeliveryPlaceholderPage(title=entry.title, subtitle=entry.tooltip)


def _build_overview(connection, *, branch_id: str, actor_user_id: str | None):
    from frontend.desktop.modules.orders_delivery.pages.overview_page import OrdersOverviewPage
    from frontend.desktop.modules.orders_delivery.presenters.overview_presenter import (
        OrdersOverviewPresenter,
    )
    return OrdersOverviewPage(OrdersOverviewPresenter(connection, branch_id=branch_id))


def _build_orders_list(connection, *, branch_id: str, actor_user_id: str | None):
    from frontend.desktop.modules.orders_delivery.pages.orders_list_page import OrdersListPage
    from frontend.desktop.modules.orders_delivery.presenters.orders_list_presenter import (
        OrdersListPresenter,
    )
    presenter = OrdersListPresenter(
        connection, branch_id=branch_id, actor_user_id=actor_user_id or "")
    return OrdersListPage(presenter)


def _build_analytics(connection, *, branch_id: str, actor_user_id: str | None):
    from frontend.desktop.modules.orders_delivery.pages.analytics_page import OrdersAnalyticsPage
    from frontend.desktop.modules.orders_delivery.presenters.analytics_presenter import (
        OrdersAnalyticsPresenter,
    )
    return OrdersAnalyticsPage(OrdersAnalyticsPresenter(connection, branch_id=branch_id))
