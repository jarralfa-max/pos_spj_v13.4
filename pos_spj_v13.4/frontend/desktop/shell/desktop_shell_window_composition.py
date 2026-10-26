"""build_application_window() — SHELL-16½ (new-shell live-wiring, piece 4a
of 4: the half of the composition-root job that has nothing to do with
authentication).

Ties together everything SHELL-8..16 built but nothing before this file
ever wired for real: `ModuleRegistry`/`RouteRegistry`/`ViewFactoryRegistry`
populated with the 9 already-migrated modules
(`sales_pos`/`customers_crm`/`finance`/`hr`/`inventory`/`products`/
`purchasing`/`transfers`/`cash_register`), `NavigationItemRegistry`
populated via `migrated_modules_navigation.py` (piece 3),
`DispatchingModuleActivator` bound to each module's own real activator
(every one of the 9 shares the identical `(*, connection,
view_factory_registry, session_context=None)` constructor shape, which is
what makes a single uniform table possible here), `ModuleLoader`,
`DesktopRouter`, `SidebarResolver` + `GlobalSidebar`, and finally
`ApplicationWindow` itself.

`service_supervisor` (SHELL-14) is wired since CRM-43 with the two background
services the live app actually needs: the CRM cycle (time-based automations
+ due reminders) and the notification-bell refresh from `notification_inbox`.
`shutdown_coordinator` (SHELL-15) is still not wired here.

Takes a `session_context` explicitly rather than building one — the
caller (the authentication half, piece 4b) is what actually has an
`ApplicationContext` to wrap in a `LegacySessionAdapter`; this file only
needs *something* satisfying the 9 modules' composition functions, not an
opinion on how it's produced.
"""
from __future__ import annotations

from backend.bootstrap.application_context import ApplicationContext
from backend.bootstrap.health.health_status import HealthReport
from frontend.desktop.modules.business_intelligence.shell_registration import (
    BUSINESS_INTELLIGENCE_MODULE_ID,
    BusinessIntelligenceModuleActivator,
    build_business_intelligence_module_descriptor,
    build_business_intelligence_route_definition,
)
from frontend.desktop.modules.losses.shell_registration import (
    LOSSES_MODULE_ID,
    LossesModuleActivator,
    build_losses_module_descriptor,
    build_losses_route_definition,
)
from frontend.desktop.modules.meat_processing.shell_registration import (
    MEAT_PROCESSING_MODULE_ID,
    MeatProcessingModuleActivator,
    build_meat_processing_module_descriptor,
    build_meat_processing_route_definition,
)
from frontend.desktop.modules.orders_delivery.shell_registration import (
    ORDERS_DELIVERY_MODULE_ID,
    OrdersDeliveryModuleActivator,
    build_orders_delivery_module_descriptor,
    build_orders_delivery_route_definition,
)
from frontend.desktop.modules.fidelidad.shell_registration import (
    FIDELIDAD_MODULE_ID,
    FidelidadModuleActivator,
    build_fidelidad_module_descriptor,
    build_fidelidad_route_definition,
)
from frontend.desktop.modules.assets.shell_registration import (
    ASSETS_MODULE_ID, AssetsModuleActivator,
    build_assets_module_descriptor, build_assets_route_definition,
)
from frontend.desktop.modules.pricing.shell_registration import (
    PRICING_MODULE_ID, PricingModuleActivator,
    build_pricing_module_descriptor, build_pricing_route_definition,
)
from frontend.desktop.modules.cash_register.shell_registration import (
    CASH_REGISTER_MODULE_ID, CashRegisterModuleActivator,
    build_cash_register_module_descriptor, build_cash_register_route_definition,
)
from frontend.desktop.modules.configuracion.shell_registration import (
    CONFIGURACION_MODULE_ID,
    ConfiguracionModuleActivator,
    build_configuracion_module_descriptor,
    build_configuracion_route_definition,
)
from frontend.desktop.modules.customers_crm.shell_registration import (
    CUSTOMERS_CRM_MODULE_ID, CustomersCrmModuleActivator,
    build_customers_crm_module_descriptor, build_customers_crm_route_definition,
)
from frontend.desktop.modules.finance.shell_registration import (
    FINANCE_MODULE_ID, FinanceModuleActivator,
    build_finance_module_descriptor, build_finance_route_definition,
)
from frontend.desktop.modules.hr.shell_registration import (
    HR_MODULE_ID, HRModuleActivator, build_hr_module_descriptor, build_hr_route_definition,
)
from frontend.desktop.modules.inventory.shell_registration import (
    INVENTORY_MODULE_ID, InventoryModuleActivator,
    build_inventory_module_descriptor, build_inventory_route_definition,
)
from frontend.desktop.modules.products.shell_registration import (
    PRODUCTS_MODULE_ID, ProductsModuleActivator,
    build_products_module_descriptor, build_products_route_definition,
)
from frontend.desktop.modules.logistics.shell_registration import (
    LOGISTICS_MODULE_ID, LogisticsModuleActivator,
    build_logistics_module_descriptor, build_logistics_route_definition,
)
from frontend.desktop.modules.purchasing.shell_registration import (
    PURCHASING_MODULE_ID, PurchasingModuleActivator,
    build_purchasing_module_descriptor, build_purchasing_route_definition,
)
from frontend.desktop.modules.sales_pos.shell_registration import (
    SALES_POS_MODULE_ID, SalesPosModuleActivator,
    build_sales_pos_module_descriptor, build_sales_pos_route_definition,
)
from frontend.desktop.modules.transfers.shell_registration import (
    TRANSFERS_MODULE_ID, TransfersModuleActivator,
    build_transfers_module_descriptor, build_transfers_route_definition,
)
from frontend.desktop.shell.application_shell.application_window import ApplicationWindow
from frontend.desktop.shell.loading.dispatching_module_activator import DispatchingModuleActivator
from frontend.desktop.shell.loading.module_loader import ModuleLoader
from frontend.desktop.shell.modules.health_requirement import ModuleHealthEvaluator
from frontend.desktop.shell.modules.module_registry import ModuleRegistry
from frontend.desktop.shell.router.desktop_router import DesktopRouter
from frontend.desktop.shell.routing.route_registry import RouteRegistry
from frontend.desktop.shell.routing.view_factory_registry import ViewFactoryRegistry
from frontend.desktop.shell.sidebar.badge_registry import BadgeRegistry
from frontend.desktop.shell.sidebar.global_sidebar import GlobalSidebar
from frontend.desktop.shell.sidebar.migrated_modules_navigation import register_migrated_modules_navigation
from frontend.desktop.shell.sidebar.navigation_item_registry import NavigationItemRegistry
from frontend.desktop.shell.sidebar.sidebar_resolver import SidebarResolver

def _standard_activator_factory(activator_cls):
    """Every migrated module's activator EXCEPT `products` shares the
    identical `(*, connection, view_factory_registry, session_context=None)`
    constructor — confirmed by reading all 9 `shell_registration.py` files
    before writing this table, not assumed."""
    return lambda connection, view_factories, session_context: activator_cls(
        connection=connection, view_factory_registry=view_factories, session_context=session_context,
    )


def _products_activator_factory(connection, view_factories, session_context):
    """`ProductsModuleActivator` does NOT accept `session_context` — it
    takes `live_session`/`branch_id_fallback` instead (see
    `frontend/desktop/modules/products/shell_registration.py`, and
    `composition.py`'s own docstring on the two-track identity split this
    mirrors). `LegacySessionAdapter` already exposes the
    `.sucursal_id`/`.user_id` attributes `products`' internal `_Session`
    wrapper reads via `getattr`, so it doubles as `live_session` here —
    `branch_id_fallback` is left at its default (None) since the adapter's
    `sucursal_id` always resolves from `ApplicationContext.branch_id` and
    never needs the fallback path."""
    return ProductsModuleActivator(
        connection=connection, view_factory_registry=view_factories, live_session=session_context,
    )


# (module_id, descriptor builder, route builder, activator factory) —
# `activator_factory(connection, view_factory_registry, session_context)`.
_MIGRATED_MODULE_WIRINGS = (
    (SALES_POS_MODULE_ID, build_sales_pos_module_descriptor, build_sales_pos_route_definition, _standard_activator_factory(SalesPosModuleActivator)),
    (CUSTOMERS_CRM_MODULE_ID, build_customers_crm_module_descriptor, build_customers_crm_route_definition, _standard_activator_factory(CustomersCrmModuleActivator)),
    (FINANCE_MODULE_ID, build_finance_module_descriptor, build_finance_route_definition, _standard_activator_factory(FinanceModuleActivator)),
    (HR_MODULE_ID, build_hr_module_descriptor, build_hr_route_definition, _standard_activator_factory(HRModuleActivator)),
    (INVENTORY_MODULE_ID, build_inventory_module_descriptor, build_inventory_route_definition, _standard_activator_factory(InventoryModuleActivator)),
    (PRODUCTS_MODULE_ID, build_products_module_descriptor, build_products_route_definition, _products_activator_factory),
    (PURCHASING_MODULE_ID, build_purchasing_module_descriptor, build_purchasing_route_definition, _standard_activator_factory(PurchasingModuleActivator)),
    (TRANSFERS_MODULE_ID, build_transfers_module_descriptor, build_transfers_route_definition, _standard_activator_factory(TransfersModuleActivator)),
    (CASH_REGISTER_MODULE_ID, build_cash_register_module_descriptor, build_cash_register_route_definition, _standard_activator_factory(CashRegisterModuleActivator)),
    (CONFIGURACION_MODULE_ID, build_configuracion_module_descriptor, build_configuracion_route_definition, _standard_activator_factory(ConfiguracionModuleActivator)),
    (BUSINESS_INTELLIGENCE_MODULE_ID, build_business_intelligence_module_descriptor, build_business_intelligence_route_definition, _standard_activator_factory(BusinessIntelligenceModuleActivator)),
    (LOSSES_MODULE_ID, build_losses_module_descriptor, build_losses_route_definition, _standard_activator_factory(LossesModuleActivator)),
    (MEAT_PROCESSING_MODULE_ID, build_meat_processing_module_descriptor, build_meat_processing_route_definition, _standard_activator_factory(MeatProcessingModuleActivator)),
    (ORDERS_DELIVERY_MODULE_ID, build_orders_delivery_module_descriptor, build_orders_delivery_route_definition, _standard_activator_factory(OrdersDeliveryModuleActivator)),
    (FIDELIDAD_MODULE_ID, build_fidelidad_module_descriptor, build_fidelidad_route_definition, _standard_activator_factory(FidelidadModuleActivator)),
    (ASSETS_MODULE_ID, build_assets_module_descriptor, build_assets_route_definition, _standard_activator_factory(AssetsModuleActivator)),
    (PRICING_MODULE_ID, build_pricing_module_descriptor, build_pricing_route_definition, _standard_activator_factory(PricingModuleActivator)),
    (LOGISTICS_MODULE_ID, build_logistics_module_descriptor, build_logistics_route_definition, _standard_activator_factory(LogisticsModuleActivator)),
)


#: Cada cuánto corre el ciclo del CRM (automatizaciones por tiempo y recordatorios).
CRM_CYCLE_INTERVAL_MS = 5 * 60 * 1000
#: Cada cuánto se refresca la campana de avisos.
INBOX_REFRESH_INTERVAL_MS = 60 * 1000
#: Cada cuánto se entrega la cola de alertas de Productos por WhatsApp (PROD-22).
PRODUCTS_WHATSAPP_OUTBOX_INTERVAL_MS = 60 * 1000
# Revisión periódica de reglas de reposición; el notifier limita repeticiones.
STOCK_MINIMUM_INTERVAL_MS = 5 * 60 * 1000
#: Cada cuánto se revisa si una actualización programada ya puede instalarse
#: (dentro de la ventana de mantenimiento y sin operaciones en curso).
SCHEDULED_UPDATE_INTERVAL_MS = 60 * 1000
#: Auditoría de Caja CJA-04 (2026-10-16): reintento de lo que Caja no pudo
#: entregar a Finanzas (Corte Z, entrega de valores).
CASH_OUTBOX_INTERVAL_MS = 2 * 60 * 1000
#: FIN-ERP (2026-10-22): merma valuada hacia el mayor, vencimientos de CxC/CxP
#: y entrega del finance_outbox.
FINANCE_CYCLE_INTERVAL_MS = 5 * 60 * 1000
#: Auditoría Fidelidad 968e0bc FID-10: ventas pendientes hacia Fidelidad y
#: Finanzas (puntos, canje, vales) tras un fallo o un cierre a media operación.
LOYALTY_SALES_INTERVAL_MS = 2 * 60 * 1000


def _build_background_services(*, context: ApplicationContext, connection):
    """CRM-43: los servicios de fondo de la sesión. Devuelve el supervisor y la
    fuente de la campana, que se conecta al cajón una vez creada la ventana."""
    from backend.application.crm.background_cycle import run_crm_background_cycle
    from backend.application.notifications.user_inbox_service import UserInboxService
    from frontend.desktop.shell.application_shell.notification_inbox_feed import (
        NotificationInboxFeed,
    )
    from frontend.desktop.shell.background.background_service_descriptor import (
        BackgroundServiceDescriptor,
    )
    from frontend.desktop.shell.background.background_service_registry import (
        BackgroundServiceRegistry,
    )
    from frontend.desktop.shell.background.background_service_supervisor import (
        BackgroundServiceSupervisor,
    )
    from frontend.desktop.shell.background.periodic_task_service import PeriodicTaskService

    registry = BackgroundServiceRegistry()
    registry.register(BackgroundServiceDescriptor(
        "crm.background_cycle", "Automatizaciones y recordatorios del CRM",
        module_id="customers_crm"))
    registry.register(BackgroundServiceDescriptor("notifications.inbox", "Bandeja de avisos"))
    registry.register(BackgroundServiceDescriptor(
        "products.whatsapp_outbox", "Alertas de Productos por WhatsApp", module_id="products"))
    registry.register(BackgroundServiceDescriptor(
        "inventory.stock_minimum", "Mínimos de stock por almacén", module_id="inventory"))
    supervisor = BackgroundServiceSupervisor(registry=registry)
    supervisor.bind("crm.background_cycle", PeriodicTaskService(
        lambda: run_crm_background_cycle(connection), interval_ms=CRM_CYCLE_INTERVAL_MS,
        name="ciclo CRM"))
    from backend.application.products.notifications.whatsapp_outbox import (
        drain_product_whatsapp_outbox,
    )
    supervisor.bind("products.whatsapp_outbox", PeriodicTaskService(
        lambda: drain_product_whatsapp_outbox(connection),
        interval_ms=PRODUCTS_WHATSAPP_OUTBOX_INTERVAL_MS, name="cola WhatsApp de Productos"))
    from backend.application.inventory.notifications.stock_minimum_monitor import (
        StockMinimumMonitor,
    )
    supervisor.bind("inventory.stock_minimum", PeriodicTaskService(
        StockMinimumMonitor(connection).run_once,
        interval_ms=STOCK_MINIMUM_INTERVAL_MS, name="mínimos de stock"))
    registry.register(BackgroundServiceDescriptor(
        "cash_register.outbox", "Entrega de Caja a Finanzas", module_id="cash_register"))
    supervisor.bind("cash_register.outbox", PeriodicTaskService(
        _cash_outbox_tick(connection), interval_ms=CASH_OUTBOX_INTERVAL_MS,
        name="cola de Caja a Finanzas"))
    # Auditoría Fidelidad 968e0bc FID-10: ventas pendientes hacia Fidelidad y
    # Finanzas se reintentan solas (antes, hasta la siguiente operación del POS).
    registry.register(BackgroundServiceDescriptor(
        "loyalty.sales_events", "Ventas pendientes hacia Fidelidad y Finanzas",
        module_id="fidelidad"))
    supervisor.bind("loyalty.sales_events", PeriodicTaskService(
        _loyalty_sales_tick(connection), interval_ms=LOYALTY_SALES_INTERVAL_MS,
        name="ventas a Fidelidad"))
    registry.register(BackgroundServiceDescriptor(
        "finance.cycle", "Merma, vencimientos y eventos de Finanzas", module_id="finance"))
    supervisor.bind("finance.cycle", PeriodicTaskService(
        _finance_cycle_tick(connection), interval_ms=FINANCE_CYCLE_INTERVAL_MS,
        name="ciclo de Finanzas"))
    registry.register(BackgroundServiceDescriptor(
        "software_updates.maintenance_window", "Actualización en la ventana de mantenimiento"))
    supervisor.bind("software_updates.maintenance_window", PeriodicTaskService(
        _scheduled_update_tick(connection), interval_ms=SCHEDULED_UPDATE_INTERVAL_MS,
        name="ventana de mantenimiento"))
    feed = NotificationInboxFeed(UserInboxService(connection), context.user_id)
    supervisor.bind("notifications.inbox", PeriodicTaskService(
        feed.refresh, interval_ms=INBOX_REFRESH_INTERVAL_MS, name="bandeja de avisos"))
    return supervisor, feed


def _cash_outbox_tick(connection):
    """Reintenta la cola de Caja hacia Finanzas (idempotente por evento)."""
    def tick():
        from backend.application.cash_register.finance_wiring import dispatch_cash_outbox
        from backend.shared.events.application_bus import get_bus
        return dispatch_cash_outbox(connection, get_bus())
    return tick


def _loyalty_sales_tick(connection):
    """sales_outbox + puente Fidelidad→Finanzas (idempotente)."""
    def tick():
        from backend.bootstrap.wiring.event_wiring import loyalty_sales_tick
        from backend.shared.events.application_bus import get_bus
        return loyalty_sales_tick(connection, get_bus())
    return tick


def _finance_cycle_tick(connection):
    """Merma valuada pendiente, vencimientos y finance_outbox (idempotente)."""
    def tick():
        from backend.application.finance.wiring import finance_periodic_tick
        from backend.shared.events.application_bus import get_bus
        return finance_periodic_tick(connection, get_bus())
    return tick


def _scheduled_update_tick(connection):
    """Lanza una actualización que alguien programó para la ventana de
    mantenimiento, sólo dentro de la ventana y sin ventas/cobros/cortes en
    curso (`RunScheduledUpdateIfDueUseCase`). El cierre lo hace `app.py`."""
    from backend.application.software_updates.use_cases import RunScheduledUpdateIfDueUseCase
    from backend.infrastructure.desktop.software_updates_factory import (
        build_software_update_dependencies,
    )
    from frontend.desktop.shell.application_lifecycle import request_update_handoff

    dependencies = build_software_update_dependencies(connection)

    def tick() -> None:
        request = RunScheduledUpdateIfDueUseCase(dependencies).execute()
        if request is not None:
            request_update_handoff(request)

    return tick


def build_application_window(
    *, context: ApplicationContext, connection, session_context, health_report: HealthReport,
) -> ApplicationWindow:
    """Build a real, live `ApplicationWindow` with all 16 migrated modules
    registered, routable, and represented in the sidebar — the same
    `connection`/`session_context` every migrated module's own
    `shell_registration.py` already expects (see that module's docstring
    for why `session_context` isn't built here)."""
    modules = ModuleRegistry()
    routes = RouteRegistry()
    view_factories = ViewFactoryRegistry()
    nav_items = NavigationItemRegistry()
    register_migrated_modules_navigation(nav_items)

    dispatcher = DispatchingModuleActivator()
    for module_id, build_descriptor, build_route, activator_factory in _MIGRATED_MODULE_WIRINGS:
        modules.register(build_descriptor())
        routes.register(build_route())
        dispatcher.register(module_id, activator_factory(connection, view_factories, session_context))

    loader = ModuleLoader(module_registry=modules, activator=dispatcher)
    router = DesktopRouter(route_registry=routes, view_factory_registry=view_factories, initial_context=context)

    resolver = SidebarResolver(
        navigation_items=nav_items, route_registry=routes, module_registry=modules,
        badge_registry=BadgeRegistry(), health_evaluator=ModuleHealthEvaluator(),
    )
    sidebar = GlobalSidebar(settings_key=f"{context.workstation_id}/{context.user_id}")
    sidebar.set_items(resolver.resolve(context=context, health_report=health_report))

    supervisor, inbox_feed = _build_background_services(context=context, connection=connection)
    window = ApplicationWindow(router=router, sidebar=sidebar, module_loader=loader,
                               service_supervisor=supervisor)
    inbox_feed.attach(window.notification_drawer)
    return window
