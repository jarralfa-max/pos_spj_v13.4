"""Desktop composition root for the Procesamiento Cárnico workspace (PROC-23).

Una sola composición sirve a los DOS anfitriones: `create_meat_processing_view`
(shell canónico, vía `MeatProcessingModuleActivator`) y
`MeatProcessingModuleHost` (adaptador del `AppContainer` legacy). §3 prohíbe
que cada uno arme el suyo.

Real pages: Órdenes (mp_processing_orders) and, since PASS 6, the record pages
backed by real tables (`_RECORD_ROUTES` + Pesajes y consumos). They are built
only when the session has an active branch: every record is branch-scoped.
Plan de producción (mp_production_plan) is real since 2026-09-25 (migración
276). Still placeholders: Alertas, Análisis and the 10
slaughter routes (no slaughter tables exist; `SLAUGHTER_ENABLED` is False). The sidebar's legacy "PRODUCCION" button
(interfaz/menu_lateral.py) still launches modulos/produccion.py; this host
is not wired into main_window.py yet — cutover only happens once page
parity is real (§4/PROC-4's own stated deferral), to avoid removing access
to still-legacy-only functionality (CLAUDE.md Regla 0).
"""

from backend.application.meat_processing.authorization import MeatProcessingAuthorizationPolicy
from backend.application.meat_processing.execution_context import (
    MeatProcessingExecutionContext,
)
from backend.application.meat_processing.integrations.products_recipe_snapshot_adapter import (
    ProductsRecipeSnapshotAdapter,
)
from backend.application.meat_processing.queries import ProcessingOrderQueryService
from backend.application.meat_processing.session_authorization import (
    MeatProcessingSessionPermissionChecker,
)
from backend.application.meat_processing.use_cases import (
    ApproveProcessingOrderUseCase,
    CloseProcessingOrderUseCase,
    CreateProcessingOrderUseCase,
    PrepareProcessingOrderUseCase,
    ReleaseProcessingOrderUseCase,
)
from backend.application.meat_processing.queries.processing_order_execution_query_service import (
    ProcessingOrderExecutionQueryService,
)
from backend.application.meat_processing.use_cases.order_execution_use_cases import (
    ExecuteProcessingOrderUseCase,
)
from backend.application.meat_processing.yield_settings import (
    UpdateYieldTolerancesUseCase,
    YieldToleranceSettingsQueryService,
)
from backend.application.security.authorizer_permission_checker import (
    AuthorizerPermissionChecker,
)
from backend.application.security.session_branch_scope import (
    assigned_branch_ids as _assigned_branches,
)
from backend.infrastructure.integrations.meat_processing_execution_ports import (
    execution_ports_factory,
    reservation_port_factory,
)
from backend.infrastructure.integrations.meat_processing_ports import (
    ProcessingOrderFolioAdapter,
)
from backend.domain.meat_processing.slaughter.feature_flag import SLAUGHTER_ENABLED
from frontend.desktop.modules.meat_processing.meat_processing_routes import (
    MEAT_PROCESSING_ROUTES,
    build_page,
)
from frontend.desktop.modules.meat_processing.navigation.meat_processing_sidebar import (
    SLAUGHTER_FEATURE_FLAG,
)
from frontend.desktop.modules.meat_processing.meat_processing_view import MeatProcessingView
from frontend.desktop.modules.meat_processing.pages import ProcessingOrdersPage
from frontend.desktop.modules.meat_processing.presenters import ProcessingOrderPresenter


def _dispatch_costing(connection) -> None:
    """Entrega en el bus los hechos que Costos dejó en su outbox (costo por
    salida → Precios; asiento de producción → Finanzas). Lo que no se entregue
    queda pendiente para el siguiente despacho."""
    from backend.application.costing.wiring import dispatch_costing_outbox
    from backend.shared.events.application_bus import get_bus
    dispatch_costing_outbox(connection, get_bus())


def _build_meat_processing_wiring(connection, session_context=None):
    """ÚNICA composición del workspace de Procesamiento Cárnico.

    Misma forma que `_build_transfers_presenter_and_permission`: recibe sólo
    lo que necesita —conexión y sesión ya desempaquetadas—, nunca el
    `AppContainer`. La consumen los dos anfitriones del módulo
    (`create_meat_processing_view` para el shell nuevo y
    `MeatProcessingModuleHost` para el slot legacy), de modo que ninguno
    pueda componer una versión propia y divergente (§3).
    """
    has_permission = (
        session_context.tiene_permiso
        if session_context is not None and hasattr(session_context, "tiene_permiso")
        else lambda _permission: False
    )
    authorization = MeatProcessingAuthorizationPolicy(
        MeatProcessingSessionPermissionChecker(session_context))

    def production_warehouse() -> tuple[str | None, str | None]:
        """El almacén del que produce la sucursal (Fase 10): el ACTIVO marcado
        «Producción» en Inventario → Almacenes. La sesión no trae almacén
        (`LegacySessionAdapter.active_warehouse_id` es ""), y sin él NINGUNA
        orden se podía crear: "Sesión sin sucursal/almacén activo"."""
        from backend.application.logistics.warehouse_directory import (
            WarehouseDirectoryQueryService,
        )
        branch = str(getattr(session_context, "active_branch_id", "") or "")
        if not branch:
            return None, "La sesión no tiene sucursal activa."
        return WarehouseDirectoryQueryService(connection).resolve_for_purpose(
            branch, "PRODUCTION")

    def _production_warehouses(branch_ids, session_warehouse: str) -> frozenset[str]:
        from backend.application.logistics.warehouse_directory import (
            WarehouseDirectoryQueryService,
        )
        directorio = WarehouseDirectoryQueryService(connection)
        almacenes = {session_warehouse} if session_warehouse else set()
        for sucursal in branch_ids:
            almacenes.update(directorio.warehouses_for_purpose(sucursal, "PRODUCTION"))
        return frozenset(almacenes)

    def context_provider() -> MeatProcessingExecutionContext:
        actor = str(getattr(session_context, "user_id", "") or "")
        branch = str(getattr(session_context, "active_branch_id", "") or "")
        # `SessionContext`/`LegacySessionAdapter` exponen
        # `active_warehouse_id`; ninguno define `warehouse_id`, así que
        # leer sólo ese alias dejaba `allowed_warehouse_ids={""}` (§17).
        # Mismo orden que ya resuelve el `ProcessingOrderPresenter` de
        # este mismo módulo.
        warehouse = str(getattr(session_context, "active_warehouse_id", None)
                        or getattr(session_context, "warehouse_id", None) or "")
        permissions = frozenset(
            code for code in getattr(session_context, "permisos", ())
            if isinstance(code, str))
        sucursales = _assigned_branches(session_context, branch)
        return MeatProcessingExecutionContext(
            actor_user_id=actor, active_branch_id=branch,
            assigned_branch_ids=sucursales,
            # Los almacenes de producción de TODAS las sucursales de alcance,
            # no sólo el de la activa: quien tiene asignada una segunda
            # sucursal aprueba allá, y el almacén de esa orden es el de allá.
            allowed_warehouse_ids=_production_warehouses(sucursales, warehouse),
            permissions=permissions,
        )

    orders_presenter = ProcessingOrderPresenter(
        connection_provider=lambda: connection,
        query_factory=ProcessingOrderQueryService,
        create_uc=CreateProcessingOrderUseCase(
            authorization, folio_port=ProcessingOrderFolioAdapter),
        approve_uc=ApproveProcessingOrderUseCase(authorization),
        # Preparar congela la definición de Productos y reserva en Inventario;
        # liberar ya no lee Productos (§2/§5).
        prepare_uc=PrepareProcessingOrderUseCase(
            authorization, recipe_snapshot_port=ProductsRecipeSnapshotAdapter(connection),
            reservation_port_factory=reservation_port_factory(connection)),
        release_uc=ReleaseProcessingOrderUseCase(authorization),
        close_uc=CloseProcessingOrderUseCase(authorization),
        session_context=session_context,
        context_provider=context_provider,
        warehouse_provider=production_warehouse,
        plan_query=lambda: ProcessingOrderExecutionQueryService(connection),
        # Ejecutar la orden (orquestación reanudable): consume lo reservado,
        # recibe salidas, pide calidad y costeo, y cierra. El AUTORIZADOR de un
        # rendimiento fuera de tolerancia es otro usuario, así que se resuelve
        # contra `rol_permisos`, no contra la sesión de quien opera.
        execute_uc=ExecuteProcessingOrderUseCase(
            authorization,
            ports_factory=execution_ports_factory(dispatch_costing=_dispatch_costing),
            authorizer_authorization=MeatProcessingAuthorizationPolicy(
                AuthorizerPermissionChecker(
                    connection,
                    branch_id=str(getattr(session_context, "active_branch_id", "") or "")
                    or None)),
            authorizer_checker=AuthorizerPermissionChecker(
                connection,
                branch_id=str(getattr(session_context, "active_branch_id", "") or "") or None)),
        credentials_verifier=_authorizer_credentials(connection),
        tolerances_query=lambda: YieldToleranceSettingsQueryService(connection),
        tolerances_uc=UpdateYieldTolerancesUseCase(authorization),
    )

    branch_id = str(getattr(session_context, "active_branch_id", "") or "")

    def page_builder(page_id: str):
        if page_id == "mp_processing_orders":
            return ProcessingOrdersPage(orders_presenter)
        # Literal a propósito: el trinquete de rutas reales lee esta tupla del
        # código. `test_meat_processing_record_pages` exige que sea `_RECORD_ROUTES`.
        if branch_id and page_id in (
                "mp_preparation", "mp_active_processing", "mp_cutting",
                "mp_derived_products", "mp_packaging_labeling", "mp_produced_lots",
                "mp_yields", "mp_quality", "mp_rework", "mp_incidents", "mp_audit"):
            return _record_page(connection, branch_id, page_id, session_context)
        if branch_id and page_id == "mp_weighings_consumptions":
            return _weighings_and_consumptions_page(connection, branch_id)
        if branch_id and page_id == "mp_overview":
            return _overview_page(connection, branch_id)
        if branch_id and page_id == "mp_traceability":
            return _traceability_page(connection, branch_id)
        if branch_id and page_id == "mp_settings":
            return _settings_page(orders_presenter)
        if branch_id and page_id == "mp_production_plan":
            return _production_plan_page(connection, session_context, authorization,
                                         context_provider, production_warehouse)
        return build_page(page_id)

    return has_permission, page_builder


#: Ruta → (registro, mensaje vacío). Título y subtítulo salen del sidebar.
_RECORD_ROUTES: dict[str, tuple[str, str]] = {
    "mp_preparation": ("PREPARATION", "No hay requerimientos de material."),
    "mp_active_processing": ("ACTIVE_PROCESSING", "No hay órdenes en ejecución."),
    "mp_cutting": ("CUTTING", "No hay salidas de despiece."),
    "mp_derived_products": ("DERIVED_PRODUCTS", "No hay salidas de productos derivados."),
    "mp_packaging_labeling": ("PACKAGING", "No hay empaques registrados."),
    "mp_produced_lots": ("PRODUCED_LOTS", "No hay lotes producidos."),
    "mp_yields": ("YIELDS", "No hay conciliaciones de rendimiento."),
    "mp_quality": ("QUALITY", "No hay salidas registradas."),
    "mp_rework": ("REWORK", "No hay órdenes de reproceso."),
    "mp_incidents": ("INCIDENTS", "No hay incidencias registradas."),
    "mp_audit": ("AUDIT", "No hay movimientos auditados en esta sucursal."),
}


def _record_presenter(connection, branch_id: str, nombre: str):
    from backend.application.meat_processing.queries.meat_processing_records_query_service import (
        MeatProcessingRecord,
    )
    from frontend.desktop.modules.meat_processing.presenters.meat_processing_record_presenter import (
        MeatProcessingRecordPresenter,
    )
    return MeatProcessingRecordPresenter(
        connection, branch_id=branch_id, record=MeatProcessingRecord[nombre])


def _record_page(connection, branch_id: str, page_id: str, session_context=None):
    from frontend.desktop.modules.meat_processing.pages.meat_processing_record_page import (
        MeatProcessingRecordPage,
    )
    if page_id == "mp_yields":
        return _yields_page(connection, branch_id)
    if page_id == "mp_quality":
        return _quality_page(connection, branch_id, session_context)
    nombre, vacio = _RECORD_ROUTES[page_id]
    entrada = MEAT_PROCESSING_ROUTES[page_id]
    return MeatProcessingRecordPage(
        _record_presenter(connection, branch_id, nombre), title=entrada.title,
        subtitle=entrada.tooltip, empty_message=vacio)


def _yields_page(connection, branch_id: str):
    """Rendimientos (Fase 10): por corte —lo que pide el §13— y por orden."""
    from frontend.desktop.modules.meat_processing.pages.meat_processing_record_page import (
        MeatProcessingRecordPage,
        YieldsPage,
    )
    entrada = MEAT_PROCESSING_ROUTES["mp_yields"]
    por_corte = MeatProcessingRecordPage(
        _record_presenter(connection, branch_id, "OUTPUT_RESULTS"), title="Por corte",
        subtitle="Esperado, real, diferencia y costo repartido de cada corte.",
        empty_message="No hay órdenes ejecutadas.")
    por_orden = MeatProcessingRecordPage(
        _record_presenter(connection, branch_id, "YIELDS"), title="Por orden",
        subtitle="Conciliación de rendimiento de la orden.",
        empty_message="No hay conciliaciones de rendimiento.")
    return YieldsPage(por_corte, por_orden, title=entrada.title, subtitle=entrada.tooltip)


def _production_plan_page(connection, session_context, authorization, context_provider,
                          warehouse_provider):
    """Plan de producción: un plan por sucursal y día; líneas manuales o
    sugeridas (reposición de Inventario, pronóstico de BI); convertir una línea
    crea la orden aprobada con su folio."""
    from backend.application.meat_processing.queries.production_plan_query_service import (
        ProductionPlanQueryService,
    )
    from backend.application.meat_processing.use_cases import (
        AddProductionPlanLineUseCase,
        ApproveProductionPlanUseCase,
        CancelProductionPlanUseCase,
        ConvertProductionPlanLineUseCase,
        CreateProductionPlanUseCase,
        GenerateProductionPlanUseCase,
        RemoveProductionPlanLineUseCase,
        SubmitProductionPlanUseCase,
    )
    from backend.infrastructure.integrations.meat_processing_plan_sources import (
        ForecastPlanSource,
        ReplenishmentPlanSource,
    )
    from frontend.desktop.modules.meat_processing.pages.production_plan_page import (
        ProductionPlanPage,
    )
    from frontend.desktop.modules.meat_processing.presenters.production_plan_presenter import (
        ProductionPlanPresenter,
    )
    entrada = MEAT_PROCESSING_ROUTES["mp_production_plan"]
    presentador = ProductionPlanPresenter(
        connection_provider=lambda: connection, session_context=session_context,
        query_factory=ProductionPlanQueryService,
        use_cases={
            "create": CreateProductionPlanUseCase(authorization),
            "add_line": AddProductionPlanLineUseCase(authorization),
            "remove_line": RemoveProductionPlanLineUseCase(authorization),
            "generate": GenerateProductionPlanUseCase(authorization),
            "submit": SubmitProductionPlanUseCase(authorization),
            "approve": ApproveProductionPlanUseCase(authorization),
            "cancel": CancelProductionPlanUseCase(authorization),
            "convert": ConvertProductionPlanLineUseCase(
                authorization, folio_port=ProcessingOrderFolioAdapter),
        },
        suggestion_sources={"REPLENISHMENT": ReplenishmentPlanSource,
                            "FORECAST": ForecastPlanSource},
        warehouse_provider=warehouse_provider, context_provider=context_provider)
    return ProductionPlanPage(presentador, title=entrada.title, subtitle=entrada.tooltip)


def _quality_page(connection, branch_id: str, session_context):
    """Calidad: lo que espera inspección (decide el INSPECTOR, con el permiso de
    Calidad de su sesión) y el registro de salidas con su estado de calidad."""
    from backend.application.meat_processing.session_authorization import (
        MeatProcessingSessionPermissionChecker,
    )
    from backend.application.quality.output_inspection import (
        DecideOutputInspectionUseCase,
        QualityAuthorizationPolicy,
    )
    from backend.application.quality.wiring import dispatch_quality_outbox
    from backend.shared.events.application_bus import get_bus
    from frontend.desktop.modules.meat_processing.pages.meat_processing_record_page import (
        MeatProcessingRecordPage,
    )
    from frontend.desktop.modules.meat_processing.pages.quality_inspection_page import (
        PendingInspectionsPage,
        QualityPage,
    )
    from frontend.desktop.modules.meat_processing.presenters.quality_inspection_presenter import (
        QualityInspectionPresenter,
    )
    entrada = MEAT_PROCESSING_ROUTES["mp_quality"]
    presentador = QualityInspectionPresenter(
        connection, branch_id=branch_id,
        actor_provider=lambda: getattr(session_context, "user_id", ""),
        decide_uc=DecideOutputInspectionUseCase(QualityAuthorizationPolicy(
            MeatProcessingSessionPermissionChecker(session_context))),
        dispatch=lambda conn: dispatch_quality_outbox(conn, get_bus()))
    salidas = MeatProcessingRecordPage(
        _record_presenter(connection, branch_id, "QUALITY"), title="Salidas",
        subtitle="Salidas producidas y su estado de calidad.",
        empty_message=_RECORD_ROUTES["mp_quality"][1])
    return QualityPage(PendingInspectionsPage(presentador), salidas, title=entrada.title,
                       subtitle=entrada.tooltip)


def _overview_page(connection, branch_id: str):
    """Resumen: los mismos contadores del sidebar, más la foto del periodo."""
    from frontend.desktop.modules.meat_processing.pages.meat_processing_overview_page import (
        MeatProcessingOverviewPage,
    )
    from frontend.desktop.modules.meat_processing.presenters.meat_processing_overview_presenter import (
        MeatProcessingOverviewPresenter,
    )
    entrada = MEAT_PROCESSING_ROUTES["mp_overview"]
    return MeatProcessingOverviewPage(
        MeatProcessingOverviewPresenter(connection, branch_id=branch_id),
        title=entrada.title, subtitle=entrada.tooltip)


def _traceability_page(connection, branch_id: str):
    """Trazabilidad: los lotes que produjo la sucursal, con la genealogía que
    guarda Inventario (`TraceabilityQueryService`), no un grafo propio."""
    from frontend.desktop.modules.meat_processing.pages.meat_traceability_page import (
        MeatTraceabilityPage,
    )
    from frontend.desktop.modules.meat_processing.presenters.meat_traceability_presenter import (
        MeatTraceabilityPresenter,
    )
    entrada = MEAT_PROCESSING_ROUTES["mp_traceability"]
    return MeatTraceabilityPage(
        MeatTraceabilityPresenter(connection, branch_id=branch_id),
        title=entrada.title, subtitle=entrada.tooltip)


def _settings_page(presenter):
    from frontend.desktop.modules.meat_processing.pages.meat_processing_settings_page import (
        MeatProcessingSettingsPage,
    )
    entrada = MEAT_PROCESSING_ROUTES["mp_settings"]
    return MeatProcessingSettingsPage(presenter, title=entrada.title, subtitle=entrada.tooltip)


def _weighings_and_consumptions_page(connection, branch_id: str):
    from frontend.desktop.modules.meat_processing.pages.meat_processing_record_page import (
        MeatProcessingRecordPage,
        WeighingsAndConsumptionsPage,
    )
    entrada = MEAT_PROCESSING_ROUTES["mp_weighings_consumptions"]
    pesajes = MeatProcessingRecordPage(
        _record_presenter(connection, branch_id, "WEIGHINGS"), title="Pesajes",
        subtitle="Pesajes de entrada, intermedios y de salida.",
        empty_message="No hay pesajes registrados.")
    consumos = MeatProcessingRecordPage(
        _record_presenter(connection, branch_id, "CONSUMPTIONS"), title="Consumos",
        subtitle="Insumos consumidos por las órdenes.",
        empty_message="No hay consumos registrados.")
    return WeighingsAndConsumptionsPage(
        pesajes, consumos, title=entrada.title, subtitle=entrada.tooltip)


def _authorizer_credentials(connection):
    """Prueba usuario y clave de quien autoriza (mismo verificador que el
    login y que el mostrador); el permiso lo revalida el caso de uso."""
    if connection is None:
        return None
    from backend.security.authentication.verify_authorizer_credentials_use_case import (
        build_authorizer_credentials_verifier,
    )
    return build_authorizer_credentials_verifier(connection).execute


def _sidebar_badges(connection, session_context) -> dict[str, int]:
    """Contadores del sidebar al abrir el módulo; antes la vista recibía `{}`.
    Sin sucursal no hay nada que contar. No se refrescan solos."""
    branch_id = str(getattr(session_context, "active_branch_id", "") or "")
    if connection is None or not branch_id:
        return {}
    from backend.application.meat_processing.queries.meat_processing_badge_query_service import (
        MeatProcessingBadgeQueryService,
    )
    return MeatProcessingBadgeQueryService(connection).get_badge_counts(branch_id)


def _has_slaughter_feature(flag: str) -> bool:
    """Las 10 entradas de sacrificio del sidebar se gobiernan con la MISMA
    constante que el dominio (`SLAUGHTER_ENABLED`), no con un `False`
    escrito a mano aquí: dos fuentes de verdad para "¿está habilitado el
    sacrificio?" se desincronizan en cuanto alguien encienda una (§3).
    """
    return SLAUGHTER_ENABLED and flag == SLAUGHTER_FEATURE_FLAG


def create_meat_processing_view(
    connection, session_context=None, *, parent=None,
) -> MeatProcessingView:
    """Equivalente de `MeatProcessingModuleHost` con dependencias explícitas —
    lo llama `MeatProcessingModuleActivator` del shell canónico.

    Antes ese activator armaba su propio
    `MeatProcessingView(page_builder=build_page)`: las 29 rutas en
    placeholder —incluida `mp_processing_orders`, que sí tiene página real—,
    sin presenter ni casos de uso, y con un `_has_permission` que sondeaba
    `has_permission`/`permissions`, atributos que ni `SessionContext` ni
    `LegacySessionAdapter` definen, así que el sidebar salía vacío.
    """
    has_permission, page_builder = _build_meat_processing_wiring(
        connection, session_context)
    return MeatProcessingView(
        has_permission=has_permission,
        badges=_sidebar_badges(connection, session_context),
        has_feature=_has_slaughter_feature, page_builder=page_builder,
        parent=parent,
    )


class MeatProcessingModuleHost(MeatProcessingView):
    """Adaptador del `AppContainer` legacy: desempaqueta el contenedor y
    delega en la composición común. No compone nada por su cuenta (§4)."""

    def __init__(self, container, parent=None) -> None:
        has_permission, page_builder = _build_meat_processing_wiring(
            container.db, getattr(container, "session", None))
        super().__init__(
            has_permission=has_permission,
            badges=_sidebar_badges(container.db, getattr(container, "session", None)),
            has_feature=_has_slaughter_feature,
            page_builder=page_builder,
            parent=parent,
        )
