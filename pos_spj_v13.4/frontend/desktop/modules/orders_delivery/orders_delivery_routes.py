"""Single route registry for every internal Pedidos y Delivery page.
Started (ORD-4) mirroring `frontend/desktop/modules/losses/losses_routes.py`
exactly — every route resolved to the same placeholder. ORD-28 wires the
first REAL pages (Resumen/Todos los pedidos/Análisis) behind an optional
`connection`; PASS 6 adds the order and delivery worklists (`order_worklists.py`,
`delivery_worklists.py`) and the delivery records
(`delivery_records_query_service.py`); the rest
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
    # PASS 6: bandejas de reparto, sobre delivery_jobs y no sobre pedidos;
    # la bandeja la decide la ruta, via _DELIVERY_WORKLIST_BY_ROUTE.
    "orders_driver_assignment": "_build_delivery_worklist",
    "orders_active_deliveries": "_build_delivery_worklist",
    "orders_failed_deliveries": "_build_delivery_worklist",
    "orders_returns": "_build_delivery_worklist",
    # PASS 6: registros de reparto (no bandejas): todo lo de la sucursal, con
    # filtro por estado; via _DELIVERY_RECORD_BY_ROUTE.
    "orders_routes": "_build_delivery_record",
    "orders_redeliveries": "_build_delivery_record",
    "orders_cash_collections": "_build_delivery_record",
    "orders_settlements": "_build_delivery_record",
    "orders_tracking": "_build_delivery_record",
    "orders_incidents": "_build_delivery_record",
    "orders_alerts": "_build_delivery_record",
    # PASS 6: Configuración = zonas de entrega, la única configuración del
    # área con datos y reglas reales (ver delivery_settings_page.py).
    "orders_settings": "_build_delivery_settings",
}


def build_page(page_id: str, connection=None, *, branch_id: str | None = None,
                actor_user_id: str | None = None, authorization=None):
    """`authorization` es la `OrdersDeliveryAuthorizationPolicy` de la sesión.
    Sin ella las páginas se construyen igual, pero toda escritura falla cerrada."""
    try:
        entry = ORDERS_DELIVERY_ROUTES[page_id]
    except KeyError as exc:
        raise KeyError(f"Unknown Orders/Delivery route: {page_id}") from exc

    builder_name = _REAL_ROUTE_BUILDERS.get(page_id)
    if connection is not None and branch_id is not None and builder_name is not None:
        return globals()[builder_name](
            connection, page_id=page_id, branch_id=branch_id, actor_user_id=actor_user_id,
            authorization=authorization)

    from frontend.desktop.modules.orders_delivery.pages import OrdersDeliveryPlaceholderPage
    return OrdersDeliveryPlaceholderPage(title=entry.title, subtitle=entry.tooltip)


def _build_overview(connection, *, page_id: str, branch_id: str, actor_user_id: str | None,
                authorization=None):
    from frontend.desktop.modules.orders_delivery.pages.overview_page import OrdersOverviewPage
    from frontend.desktop.modules.orders_delivery.presenters.overview_presenter import (
        OrdersOverviewPresenter,
    )
    return OrdersOverviewPage(OrdersOverviewPresenter(connection, branch_id=branch_id))


def _build_orders_list(connection, *, page_id: str, branch_id: str, actor_user_id: str | None,
                authorization=None):
    from frontend.desktop.modules.orders_delivery.pages.orders_list_page import OrdersListPage
    from frontend.desktop.modules.orders_delivery.presenters.orders_list_presenter import (
        OrdersListPresenter,
    )
    presenter = OrdersListPresenter(
        connection, branch_id=branch_id, actor_user_id=actor_user_id or "",
        authorization=authorization)
    return OrdersListPage(presenter)


def _build_analytics(connection, *, page_id: str, branch_id: str, actor_user_id: str | None,
                authorization=None):
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
                          actor_user_id: str | None,
                authorization=None):
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


#: Qué bandeja de REPARTO abre cada ruta. Van sobre `delivery_jobs`, no sobre
#: pedidos: ver `delivery_worklists.py`.
_DELIVERY_WORKLIST_BY_ROUTE: dict[str, tuple[str, str]] = {
    "orders_driver_assignment": (
        "PENDING_DRIVER_ASSIGNMENT", "No hay entregas esperando repartidor."),
    "orders_active_deliveries": (
        "ACTIVE_DELIVERIES", "No hay entregas en curso."),
    "orders_failed_deliveries": (
        "FAILED_DELIVERIES", "No hay entregas fallidas pendientes de decisión."),
    "orders_returns": (
        "RETURNED_TO_BRANCH", "No hay devoluciones a sucursal."),
}


def _build_delivery_worklist(connection, *, page_id: str, branch_id: str,
                             actor_user_id: str | None,
                authorization=None):
    from backend.application.orders_delivery.queries.delivery_worklists import DeliveryWorklist
    from frontend.desktop.modules.orders_delivery.pages.delivery_job_worklist_page import (
        DeliveryJobWorklistPage,
    )
    from frontend.desktop.modules.orders_delivery.presenters.delivery_job_worklist_presenter import (
        DeliveryJobWorklistPresenter,
    )
    nombre, vacio = _DELIVERY_WORKLIST_BY_ROUTE[page_id]
    entrada = ORDERS_DELIVERY_ROUTES[page_id]
    presenter = DeliveryJobWorklistPresenter(
        connection, branch_id=branch_id, worklist=DeliveryWorklist[nombre])
    return DeliveryJobWorklistPage(
        presenter, title=entrada.title, subtitle=entrada.tooltip, empty_message=vacio)


#: Qué registro de reparto abre cada ruta, y qué dice cuando está vacío.
_DELIVERY_RECORD_BY_ROUTE: dict[str, tuple[str, str]] = {
    "orders_routes": ("ROUTES", "No hay rutas de reparto."),
    "orders_redeliveries": ("REDELIVERIES", "No hay solicitudes de reentrega."),
    "orders_cash_collections": ("CASH_COLLECTIONS", "No hay cobros en ruta registrados."),
    "orders_settlements": ("SETTLEMENTS", "No hay liquidaciones de repartidores."),
    "orders_tracking": ("TRACKING", "No hay pedidos con reparto que seguir."),
    "orders_incidents": ("INCIDENTS", "No hay intentos de entrega fallidos."),
    "orders_alerts": ("ALERTS", "No tienes alertas de reparto."),
}


def _build_delivery_record(connection, *, page_id: str, branch_id: str,
                           actor_user_id: str | None,
                authorization=None):
    from backend.application.orders_delivery.queries.delivery_records_query_service import (
        DeliveryRecord,
    )
    from frontend.desktop.modules.orders_delivery.pages.delivery_record_page import (
        DeliveryRecordPage,
    )
    from frontend.desktop.modules.orders_delivery.presenters.delivery_record_presenter import (
        DeliveryRecordPresenter,
    )
    nombre, vacio = _DELIVERY_RECORD_BY_ROUTE[page_id]
    entrada = ORDERS_DELIVERY_ROUTES[page_id]
    presenter = DeliveryRecordPresenter(
        connection, branch_id=branch_id, record=DeliveryRecord[nombre],
        # Sólo Alertas lo usa: la bandeja de notificaciones es por persona.
        recipient_user_id=actor_user_id)
    return DeliveryRecordPage(
        presenter, title=entrada.title, subtitle=entrada.tooltip, empty_message=vacio)


def _build_delivery_settings(connection, *, page_id: str, branch_id: str,
                             actor_user_id: str | None, authorization=None):
    from frontend.desktop.modules.orders_delivery.pages.delivery_settings_page import (
        DeliverySettingsPage,
    )
    from frontend.desktop.modules.orders_delivery.presenters.delivery_settings_presenter import (
        DeliverySettingsPresenter,
    )
    entrada = ORDERS_DELIVERY_ROUTES[page_id]
    presenter = DeliverySettingsPresenter(
        connection, branch_id=branch_id, actor_user_id=actor_user_id,
        authorization=authorization)
    return DeliverySettingsPage(
        presenter, title=entrada.title, subtitle=entrada.tooltip,
        empty_message=("No hay zonas de entrega. Sin zonas, ningún pedido a domicilio "
                       "puede resolver su costo de envío."))
