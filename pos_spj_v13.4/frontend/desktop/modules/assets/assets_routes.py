"""Navigation model for the Activos desktop workspace (ASSET-16, §9-10).

Mirrors ``frontend/desktop/modules/customers_crm/customers_crm_routes.py``'s
shape (route dataclass + ``visible_routes``/``grouped_routes``). All 33
route ids are §9's canonical list verbatim — every one is declared here even
though only 3 have a real page as of ASSET-16/17/18 (dashboard, directory,
detail); ``assets_workspace.py`` resolves any route without a built page to
a canonical ``ViewState.EMPTY`` placeholder, never to ``None``.

Where §8's prose sidebar grouping and §9's route list don't line up 1:1 in
the master prompt's condensed text (e.g. "Custodia" appears under both the
"Activos" and "Movimientos" sections in different phrasings), the grouping
below is this phase's own best-effort semantic interpretation — same
documented imperfection ``customers_crm_routes.py`` already accepted for its
own module.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.application.assets.permissions import AssetPermissions
from frontend.desktop.modules.assets.view_models import AssetsCapabilities


@dataclass(frozen=True)
class AssetRoute:
    route_id: str
    label: str
    group: str
    tooltip: str
    required_permission: str
    capability: str


ASSET_ROUTES: tuple[AssetRoute, ...] = (
    # -- Resumen ---------------------------------------------------------------
    AssetRoute(route_id="assets.overview", label="Resumen", group="Resumen",
              tooltip="Indicadores y alertas generales de Activos.",
              required_permission=AssetPermissions.DASHBOARD_VIEW, capability="module_view"),

    # -- Activos -----------------------------------------------------------------
    AssetRoute(route_id="assets.directory", label="Directorio", group="Activos",
              tooltip="Listado y búsqueda de activos.",
              required_permission=AssetPermissions.VIEW, capability="activos"),
    AssetRoute(route_id="assets.create", label="Alta de activo", group="Activos",
              tooltip="Registro de un nuevo activo.",
              required_permission=AssetPermissions.CREATE, capability="activos"),
    AssetRoute(route_id="assets.detail", label="Detalle de activo", group="Activos",
              tooltip="Expediente de un activo.",
              required_permission=AssetPermissions.VIEW, capability="activos"),
    AssetRoute(route_id="assets.categories", label="Categorías", group="Activos",
              tooltip="Catálogo de categorías de activos.",
              required_permission=AssetPermissions.SETTINGS_VIEW, capability="activos"),
    AssetRoute(route_id="assets.locations", label="Ubicaciones", group="Activos",
              tooltip="Jerarquía de ubicaciones físicas.",
              required_permission=AssetPermissions.SETTINGS_VIEW, capability="activos"),
    AssetRoute(route_id="assets.custody", label="Custodia", group="Activos",
              tooltip="Custodia y responsables por activo.",
              required_permission=AssetPermissions.CUSTODY_VIEW, capability="activos"),
    AssetRoute(route_id="assets.assignments", label="Responsables", group="Activos",
              tooltip="Historial de asignaciones.",
              required_permission=AssetPermissions.CUSTODY_VIEW, capability="activos"),
    AssetRoute(route_id="assets.tags", label="Etiquetas y QR", group="Activos",
              tooltip="Etiquetas y códigos QR/barras.",
              required_permission=AssetPermissions.TAG_VIEW, capability="activos"),

    # -- Mantenimiento -------------------------------------------------------
    AssetRoute(route_id="assets.maintenance.overview", label="Resumen", group="Mantenimiento",
              tooltip="Resumen de mantenimiento.",
              required_permission=AssetPermissions.MAINTENANCE_VIEW, capability="mantenimiento"),
    AssetRoute(route_id="assets.maintenance.plan", label="Plan preventivo", group="Mantenimiento",
              tooltip="Planes de mantenimiento preventivo.",
              required_permission=AssetPermissions.MAINTENANCE_PLAN_VIEW, capability="mantenimiento"),
    AssetRoute(route_id="assets.maintenance.work_orders", label="Órdenes de trabajo",
              group="Mantenimiento", tooltip="Órdenes de trabajo de mantenimiento.",
              required_permission=AssetPermissions.WORK_ORDER_VIEW, capability="mantenimiento"),
    AssetRoute(route_id="assets.maintenance.calendar", label="Agenda", group="Mantenimiento",
              tooltip="Calendario de mantenimiento.",
              required_permission=AssetPermissions.WORK_ORDER_VIEW, capability="mantenimiento"),
    AssetRoute(route_id="assets.maintenance.corrective", label="Correctivos", group="Mantenimiento",
              tooltip="Órdenes de mantenimiento correctivo.",
              required_permission=AssetPermissions.WORK_ORDER_VIEW, capability="mantenimiento"),
    AssetRoute(route_id="assets.maintenance.inspections", label="Inspecciones",
              group="Mantenimiento", tooltip="Inspecciones programadas y ejecutadas.",
              required_permission=AssetPermissions.INSPECTION_VIEW, capability="mantenimiento"),
    AssetRoute(route_id="assets.maintenance.overdue", label="Vencidos", group="Mantenimiento",
              tooltip="Mantenimientos vencidos.",
              required_permission=AssetPermissions.WORK_ORDER_VIEW, capability="mantenimiento"),
    AssetRoute(route_id="assets.maintenance.history", label="Historial", group="Mantenimiento",
              tooltip="Historial de mantenimiento.",
              required_permission=AssetPermissions.MAINTENANCE_VIEW, capability="mantenimiento"),

    # -- Costos y vida útil ----------------------------------------------------
    AssetRoute(route_id="assets.costs", label="Costos operativos", group="Costos y vida útil",
              tooltip="Costos operativos por activo.",
              required_permission=AssetPermissions.COST_VIEW, capability="costos"),
    AssetRoute(route_id="assets.improvements", label="Mejoras", group="Costos y vida útil",
              tooltip="Mejoras registradas.",
              required_permission=AssetPermissions.COST_VIEW, capability="costos"),
    AssetRoute(route_id="assets.capitalization_proposals", label="Capitalizaciones propuestas",
              group="Costos y vida útil", tooltip="Propuestas de capitalización.",
              required_permission=AssetPermissions.CAPITALIZATION_PROPOSAL_VIEW, capability="costos"),
    AssetRoute(route_id="assets.depreciation_projection", label="Valor proyectado",
              group="Costos y vida útil", tooltip="Proyección financiera de solo lectura.",
              required_permission=AssetPermissions.FINANCIAL_PROJECTION_VIEW, capability="costos"),

    # -- Movimientos -------------------------------------------------------------
    AssetRoute(route_id="assets.movements", label="Asignaciones", group="Movimientos",
              tooltip="Asignaciones activas.",
              required_permission=AssetPermissions.CUSTODY_VIEW, capability="movimientos"),
    AssetRoute(route_id="assets.transfers", label="Transferencias", group="Movimientos",
              tooltip="Transferencias entre sucursales.",
              required_permission=AssetPermissions.TRANSFER_VIEW, capability="movimientos"),
    AssetRoute(route_id="assets.loans", label="Préstamos", group="Movimientos",
              tooltip="Préstamos temporales.",
              required_permission=AssetPermissions.CUSTODY_VIEW, capability="movimientos"),

    # -- Control físico ------------------------------------------------------
    AssetRoute(route_id="assets.physical_inventory", label="Inventario físico",
              group="Control físico", tooltip="Campañas de conteo físico.",
              required_permission=AssetPermissions.PHYSICAL_INVENTORY_VIEW, capability="control_fisico"),
    AssetRoute(route_id="assets.physical_counts", label="Conteos", group="Control físico",
              tooltip="Escaneos de un conteo.",
              required_permission=AssetPermissions.PHYSICAL_INVENTORY_VIEW, capability="control_fisico"),
    AssetRoute(route_id="assets.missing", label="Diferencias", group="Control físico",
              tooltip="Diferencias detectadas.",
              required_permission=AssetPermissions.DISCREPANCY_VIEW, capability="control_fisico"),

    # -- Documentación -------------------------------------------------------
    AssetRoute(route_id="assets.documents", label="Documentos", group="Documentación",
              tooltip="Facturas, manuales, fotografías, certificados.",
              required_permission=AssetPermissions.DOCUMENT_VIEW, capability="documentacion"),
    AssetRoute(route_id="assets.warranties", label="Garantías", group="Documentación",
              tooltip="Garantías por activo.",
              required_permission=AssetPermissions.WARRANTY_VIEW, capability="documentacion"),
    AssetRoute(route_id="assets.insurance", label="Seguros", group="Documentación",
              tooltip="Pólizas de seguro por activo.",
              required_permission=AssetPermissions.INSURANCE_VIEW, capability="documentacion"),

    # -- Bajas ---------------------------------------------------------------
    AssetRoute(route_id="assets.disposals", label="Solicitudes", group="Bajas",
              tooltip="Solicitudes de baja.",
              required_permission=AssetPermissions.DISPOSAL_VIEW, capability="bajas"),
    AssetRoute(route_id="assets.disposal_requests", label="Aprobaciones", group="Bajas",
              tooltip="Bajas pendientes de aprobación.",
              required_permission=AssetPermissions.DISPOSAL_REVIEW, capability="bajas"),
    AssetRoute(route_id="assets.disposal_history", label="Historial", group="Bajas",
              tooltip="Historial de bajas.",
              required_permission=AssetPermissions.DISPOSAL_VIEW, capability="bajas"),

    # -- Control ---------------------------------------------------------------
    AssetRoute(route_id="assets.alerts", label="Alertas", group="Control",
              tooltip="Alertas del módulo.",
              required_permission=AssetPermissions.DASHBOARD_VIEW, capability="control"),
    AssetRoute(route_id="assets.audit", label="Auditoría", group="Control",
              tooltip="Bitácora de auditoría del módulo.",
              required_permission=AssetPermissions.AUDIT_VIEW, capability="control"),
    AssetRoute(route_id="assets.settings", label="Configuración", group="Control",
              tooltip="Configuración del módulo de Activos.",
              required_permission=AssetPermissions.SETTINGS_VIEW, capability="control"),
)


def visible_routes(capabilities: AssetsCapabilities) -> tuple[AssetRoute, ...]:
    """Return routes authorized by UI capabilities, not raw route permissions."""
    if not capabilities.module_view:
        return ()
    return tuple(
        route for route in ASSET_ROUTES
        if bool(getattr(capabilities, route.capability, False)))


def grouped_routes(
    routes: tuple[AssetRoute, ...] | list[AssetRoute] | None = None,
) -> list[tuple[str, list[AssetRoute]]]:
    groups: list[tuple[str, list[AssetRoute]]] = []
    for route in ASSET_ROUTES if routes is None else routes:
        if not groups or groups[-1][0] != route.group:
            groups.append((route.group, []))
        groups[-1][1].append(route)
    return groups
