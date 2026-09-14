"""Single route registry for every internal Pedidos y Delivery page.
Started (ORD-4) mirroring `frontend/desktop/modules/losses/losses_routes.py`
exactly — every route resolved to the same placeholder. ORD-28 wires the
first REAL pages (Resumen/Todos los pedidos/Análisis) behind an optional
`connection`; PASS 6 adds the six order worklists (see `order_worklists.py`); the rest
stay placeholders, an honest,
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
    # PASS 6: bandejas de pedidos. Una sola clase de pagina; la bandeja la
    # decide la ruta, via _WORKLIST_BY_ROUTE al final de este archivo.
    "orders_scheduled": "_build_order_worklist",
    "orders_pending_confirmation": "_build_order_worklist",
    "orders_preparation": "_build_order_worklist",
    "orders_weight_adjustments": "_build_order_worklist",
    "orders_ready_pickup": "_build_order_worklist",
    "orders_ready_dispatch": "_build_order_worklist",
}


def build_page(page_id: str, connection=None, *, branch_id: str | None = None,
                actor_user_id: str | None = None):
    try:
        entry = ORDERS_DELIVERY_ROUTES[page_id]
    except KeyError as exc:
        raise KeyError(f"Unknown Orders/Delivery route: {page_id}") from exc

    builder_name = _REAL_ROUTE_BUILDERS.get(page_id)
    if connection is not None and branch_id is not None and builder_name is not None:
        return globals()[builder_name](
            connection, page_id=page_id, branch_id=branch_id, actor_user_id=actor_user_id)

    from frontend.desktop.modules.orders_delivery.pages import OrdersDeliveryPlaceholderPage
    return OrdersDeliveryPlaceholderPage(title=entry.title, subtitle=entry.tooltip)


def _build_overview(connection, *, page_id: str, branch_id: str, actor_user_id: str | None):
    from frontend.desktop.modules.orders_delivery.pages.overview_page import OrdersOverviewPage
    from frontend.desktop.modules.orders_delivery.presenters.overview_presenter import (
        OrdersOverviewPresenter,
    )
    return OrdersOverviewPage(OrdersOverviewPresenter(connection, branch_id=branch_id))


def _build_orders_list(connection, *, page_id: str, branch_id: str, actor_user_id: str | None):
    from frontend.desktop.modules.orders_delivery.pages.orders_list_page import OrdersListPage
    from frontend.desktop.modules.orders_delivery.presenters.orders_list_presenter import (
        OrdersListPresenter,
    )
    presenter = OrdersListPresenter(
        connection, branch_id=branch_id, actor_user_id=actor_user_id or "")
    return OrdersListPage(presenter)


def _build_analytics(connection, *, page_id: str, branch_id: str, actor_user_id: str | None):
    from frontend.desktop.modules.orders_delivery.pages.analytics_page import OrdersAnalyticsPage
    from frontend.desktop.modules.orders_delivery.presenters.analytics_presenter import (
        OrdersAnalyticsPresenter,
    )
    return OrdersAnalyticsPage(OrdersAnalyticsPresenter(connection, branch_id=branch_id))


#: Qué bandeja abre cada ruta, y qué dice cuando está vacía. El título y el
#: subtítulo NO se repiten aquí: salen de la entrada del sidebar, para que el
#: menú y la pantalla no puedan llamar distinto a lo mismo.
_WORKLIST_BY_ROUTE: dict[str, tuple[str, str]] = {
    "orders_scheduled": (
        "SCHEDULED_PENDING_ACTIVATION", "No hay pedidos programados pendientes de activación."),
    "orders_pending_confirmation": (
        "PENDING_CONFIRMATION", "No hay pedidos esperando confirmación."),
    "orders_preparation": (
        "PREPARATION_QUEUE", "No hay pedidos en la cola de preparación."),
    "orders_weight_adjustments": (
        "WEIGHT_ADJUSTMENTS_PENDING", "No hay ajustes de peso pendientes de aprobación."),
    "orders_ready_pickup": (
        "READY_FOR_PICKUP", "No hay pedidos listos para recoger."),
    "orders_ready_dispatch": (
        "READY_FOR_DISPATCH", "No hay pedidos listos para despacho."),
}


def _build_order_worklist(connection, *, page_id: str, branch_id: str,
                          actor_user_id: str | None):
    from backend.application.orders_delivery.queries.order_worklists import OrderWorklist
    from frontend.desktop.modules.orders_delivery.pages.order_worklist_page import (
        OrderWorklistPage,
    )
    from frontend.desktop.modules.orders_delivery.presenters.order_worklist_presenter import (
        OrderWorklistPresenter,
    )
    nombre, vacio = _WORKLIST_BY_ROUTE[page_id]
    entrada = ORDERS_DELIVERY_ROUTES[page_id]
    presenter = OrderWorklistPresenter(
        connection, branch_id=branch_id, worklist=OrderWorklist[nombre])
    return OrderWorklistPage(
        presenter, title=entrada.title, subtitle=entrada.tooltip, empty_message=vacio)
