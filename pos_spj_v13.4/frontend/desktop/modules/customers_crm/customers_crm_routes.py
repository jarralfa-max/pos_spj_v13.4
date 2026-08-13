"""Navigation model for the Clientes y CRM desktop workspace (CRM-14).

Mirrors ``frontend/desktop/modules/cash_register/cash_register_routes.py``'s
shape (route dataclass + ``visible_routes``/``grouped_routes``), with one
deliberate difference: the field is named ``route_id`` (cash_register calls
it ``key``) because the CRM-1 routes-are-stable guardrail requires that
literal field name to be assigned as a keyword argument on every declared
route.

All 61 route ids are §9's full canonical list verbatim (master prompt
``docs/refactor/customers_crm_master_prompt.md`` §9) — every one is
declared here even though most don't have a real page yet (CRM-14 is UI
*foundations*; ``customers_crm_workspace.py`` resolves any route without a
built page to a canonical ``ViewState.EMPTY`` placeholder, never to
``None``, satisfying the guardrail and giving every nav item a working
destination today). Grouping and Spanish labels follow §8's internal
navigation groups; where §8's prose label list and §9's route list don't
line up 1:1 in the master prompt's condensed text, the pairing below is
this phase's own best-effort, semantic interpretation (documented in
``docs/refactor/CRM-14_ui_foundations.md``), not a literal transcription.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.application.crm.permissions import CRMPermissions
from backend.application.customers.permissions import CustomerPermissions
from frontend.desktop.modules.customers_crm.view_models import CustomerCrmCapabilities


@dataclass(frozen=True)
class CustomerCrmRoute:
    route_id: str
    label: str
    group: str
    tooltip: str
    required_permission: str
    capability: str


CUSTOMER_CRM_ROUTES: tuple[CustomerCrmRoute, ...] = (
    # -- Resumen -------------------------------------------------------------
    CustomerCrmRoute(
        route_id="customers.overview", label="Resumen", group="Resumen",
        tooltip="Estado general del cliente y KPIs del módulo.",
        required_permission=CustomerPermissions.ACCESS, capability="module_view"),

    # -- Clientes --------------------------------------------------------------
    CustomerCrmRoute(
        route_id="customers.directory", label="Directorio", group="Clientes",
        tooltip="Listado y búsqueda de clientes.",
        required_permission=CustomerPermissions.VIEW, capability="clientes"),
    CustomerCrmRoute(
        route_id="customers.create", label="Alta rápida", group="Clientes",
        tooltip="Alta rápida de un nuevo cliente.",
        required_permission=CustomerPermissions.VIEW, capability="clientes"),
    CustomerCrmRoute(
        route_id="customers.profile", label="Expedientes", group="Clientes",
        tooltip="Expediente 360 del cliente.",
        required_permission=CustomerPermissions.VIEW, capability="clientes"),
    CustomerCrmRoute(
        route_id="customers.accounts", label="Cuentas comerciales", group="Clientes",
        tooltip="Cuentas y jerarquía comercial.",
        required_permission=CustomerPermissions.VIEW, capability="clientes"),
    CustomerCrmRoute(
        route_id="customers.contacts", label="Contactos", group="Clientes",
        tooltip="Personas de contacto del cliente.",
        required_permission=CustomerPermissions.VIEW, capability="clientes"),
    CustomerCrmRoute(
        route_id="customers.addresses", label="Direcciones", group="Clientes",
        tooltip="Direcciones fiscales y de entrega.",
        required_permission=CustomerPermissions.VIEW, capability="clientes"),
    CustomerCrmRoute(
        route_id="customers.tax_profiles", label="Datos fiscales", group="Clientes",
        tooltip="Perfil fiscal (RFC, régimen, CFDI).",
        required_permission=CustomerPermissions.VIEW, capability="clientes"),
    CustomerCrmRoute(
        route_id="customers.duplicates", label="Duplicados", group="Clientes",
        tooltip="Candidatos a duplicado y fusión.",
        required_permission=CustomerPermissions.VIEW, capability="clientes"),

    # -- Prospectos --------------------------------------------------------------
    CustomerCrmRoute(
        route_id="crm.leads", label="Prospectos", group="Prospectos",
        tooltip="Directorio de leads.",
        required_permission=CRMPermissions.LEADS_VIEW, capability="prospectos"),
    CustomerCrmRoute(
        route_id="crm.lead_detail", label="Detalle de lead", group="Prospectos",
        tooltip="Expediente de un lead.",
        required_permission=CRMPermissions.LEADS_VIEW, capability="prospectos"),
    CustomerCrmRoute(
        route_id="crm.lead_qualification", label="Calificación", group="Prospectos",
        tooltip="Calificación de leads (BANT, score, manual).",
        required_permission=CRMPermissions.LEADS_VIEW, capability="prospectos"),
    CustomerCrmRoute(
        route_id="crm.lead_conversion", label="Conversión", group="Prospectos",
        tooltip="Conversión de lead a cliente/oportunidad.",
        required_permission=CRMPermissions.LEADS_VIEW, capability="prospectos"),
    CustomerCrmRoute(
        route_id="crm.leads_discarded", label="Leads descartados", group="Prospectos",
        tooltip="Leads no calificados o perdidos.",
        required_permission=CRMPermissions.LEADS_VIEW, capability="prospectos"),

    # -- Oportunidades -------------------------------------------------------
    CustomerCrmRoute(
        route_id="crm.pipeline", label="Pipeline", group="Oportunidades",
        tooltip="Vista del pipeline comercial.",
        required_permission=CRMPermissions.OPPORTUNITIES_VIEW, capability="oportunidades"),
    CustomerCrmRoute(
        route_id="crm.opportunities", label="Oportunidades", group="Oportunidades",
        tooltip="Directorio de oportunidades.",
        required_permission=CRMPermissions.OPPORTUNITIES_VIEW, capability="oportunidades"),
    CustomerCrmRoute(
        route_id="crm.opportunity_detail", label="Detalle de oportunidad", group="Oportunidades",
        tooltip="Expediente de una oportunidad.",
        required_permission=CRMPermissions.OPPORTUNITIES_VIEW, capability="oportunidades"),
    CustomerCrmRoute(
        route_id="crm.forecast", label="Pronóstico comercial", group="Oportunidades",
        tooltip="Pronóstico ponderado por etapa.",
        required_permission=CRMPermissions.OPPORTUNITIES_VIEW, capability="oportunidades"),
    CustomerCrmRoute(
        route_id="crm.lost_opportunities", label="Oportunidades perdidas", group="Oportunidades",
        tooltip="Oportunidades cerradas como perdidas.",
        required_permission=CRMPermissions.OPPORTUNITIES_VIEW, capability="oportunidades"),

    # -- Actividades -----------------------------------------------------------
    CustomerCrmRoute(
        route_id="crm.calendar", label="Agenda", group="Actividades",
        tooltip="Calendario de actividades y tareas.",
        required_permission=CRMPermissions.ACTIVITIES_VIEW, capability="actividades"),
    CustomerCrmRoute(
        route_id="crm.tasks", label="Tareas", group="Actividades",
        tooltip="Tareas pendientes y completadas.",
        required_permission=CRMPermissions.ACTIVITIES_VIEW, capability="actividades"),
    CustomerCrmRoute(
        route_id="crm.calls", label="Llamadas", group="Actividades",
        tooltip="Registro de llamadas.",
        required_permission=CRMPermissions.ACTIVITIES_VIEW, capability="actividades"),
    CustomerCrmRoute(
        route_id="crm.meetings", label="Reuniones", group="Actividades",
        tooltip="Registro de reuniones.",
        required_permission=CRMPermissions.ACTIVITIES_VIEW, capability="actividades"),
    CustomerCrmRoute(
        route_id="crm.visits", label="Visitas", group="Actividades",
        tooltip="Registro de visitas.",
        required_permission=CRMPermissions.ACTIVITIES_VIEW, capability="actividades"),
    CustomerCrmRoute(
        route_id="crm.activities", label="Notas", group="Actividades",
        tooltip="Notas y actividad general.",
        required_permission=CRMPermissions.ACTIVITIES_VIEW, capability="actividades"),
    CustomerCrmRoute(
        route_id="crm.followups", label="Seguimientos", group="Actividades",
        tooltip="Recordatorios y seguimientos.",
        required_permission=CRMPermissions.ACTIVITIES_VIEW, capability="actividades"),

    # -- Atención al cliente -------------------------------------------------
    CustomerCrmRoute(
        route_id="crm.service_cases", label="Casos", group="Atención al cliente",
        tooltip="Bandeja de casos de atención.",
        required_permission=CRMPermissions.CASES_VIEW, capability="atencion"),
    CustomerCrmRoute(
        route_id="crm.case_detail", label="Detalle de caso", group="Atención al cliente",
        tooltip="Expediente de un caso.",
        required_permission=CRMPermissions.CASES_VIEW, capability="atencion"),
    CustomerCrmRoute(
        route_id="crm.complaints", label="Quejas", group="Atención al cliente",
        tooltip="Casos tipo queja.",
        required_permission=CRMPermissions.CASES_VIEW, capability="atencion"),
    CustomerCrmRoute(
        route_id="crm.requests", label="Solicitudes", group="Atención al cliente",
        tooltip="Casos tipo solicitud.",
        required_permission=CRMPermissions.CASES_VIEW, capability="atencion"),
    CustomerCrmRoute(
        route_id="crm.incidents", label="Incidencias", group="Atención al cliente",
        tooltip="Casos tipo incidencia.",
        required_permission=CRMPermissions.CASES_VIEW, capability="atencion"),
    CustomerCrmRoute(
        route_id="crm.sla", label="SLA", group="Atención al cliente",
        tooltip="Cumplimiento de niveles de servicio.",
        required_permission=CRMPermissions.CASES_VIEW, capability="atencion"),
    CustomerCrmRoute(
        route_id="crm.escalations", label="Casos escalados", group="Atención al cliente",
        tooltip="Casos escalados y su historial.",
        required_permission=CRMPermissions.CASES_VIEW, capability="atencion"),

    # -- Relación comercial ----------------------------------------------------
    CustomerCrmRoute(
        route_id="customers.purchase_history", label="Compras", group="Relación comercial",
        tooltip="Historial de compras del cliente.",
        required_permission=CustomerPermissions.ORDERS_VIEW, capability="comercial"),
    CustomerCrmRoute(
        route_id="customers.order_history", label="Pedidos", group="Relación comercial",
        tooltip="Historial de pedidos.",
        required_permission=CustomerPermissions.ORDERS_VIEW, capability="comercial"),
    CustomerCrmRoute(
        route_id="customers.quote_history", label="Cotizaciones", group="Relación comercial",
        tooltip="Historial de cotizaciones.",
        required_permission=CustomerPermissions.ORDERS_VIEW, capability="comercial"),
    CustomerCrmRoute(
        route_id="customers.return_history", label="Devoluciones", group="Relación comercial",
        tooltip="Historial de devoluciones.",
        required_permission=CustomerPermissions.ORDERS_VIEW, capability="comercial"),
    CustomerCrmRoute(
        route_id="customers.product_affinity", label="Productos frecuentes", group="Relación comercial",
        tooltip="Productos de mayor afinidad.",
        required_permission=CustomerPermissions.ORDERS_VIEW, capability="comercial"),

    # -- Crédito ---------------------------------------------------------------
    CustomerCrmRoute(
        route_id="customers.credit_requests", label="Solicitudes", group="Crédito",
        tooltip="Solicitudes de crédito.",
        required_permission=CustomerPermissions.CREDIT_VIEW, capability="credito"),
    CustomerCrmRoute(
        route_id="customers.credit_profiles", label="Perfiles de crédito", group="Crédito",
        tooltip="Perfiles y límites de crédito.",
        required_permission=CustomerPermissions.CREDIT_VIEW, capability="credito"),
    CustomerCrmRoute(
        route_id="customers.credit_exposure", label="Exposición", group="Crédito",
        tooltip="Exposición y crédito disponible.",
        required_permission=CustomerPermissions.CREDIT_VIEW, capability="credito"),
    CustomerCrmRoute(
        route_id="customers.accounts_receivable", label="Cuentas por cobrar", group="Crédito",
        tooltip="Saldo y documentos por cobrar.",
        required_permission=CustomerPermissions.CREDIT_VIEW, capability="credito"),
    CustomerCrmRoute(
        route_id="customers.credit_history", label="Historial", group="Crédito",
        tooltip="Historial de movimientos de crédito.",
        required_permission=CustomerPermissions.CREDIT_VIEW, capability="credito"),
    CustomerCrmRoute(
        route_id="customers.credit_alerts", label="Alertas", group="Crédito",
        tooltip="Alertas de vencimiento y riesgo.",
        required_permission=CustomerPermissions.CREDIT_VIEW, capability="credito"),

    # -- Segmentación ------------------------------------------------------------
    CustomerCrmRoute(
        route_id="customers.segments", label="Segmentos", group="Segmentación",
        tooltip="Segmentos de clientes.",
        required_permission=CRMPermissions.SEGMENTS_VIEW, capability="segmentacion"),
    CustomerCrmRoute(
        route_id="customers.tags", label="Etiquetas", group="Segmentación",
        tooltip="Etiquetas asignables a clientes.",
        required_permission=CRMPermissions.SEGMENTS_VIEW, capability="segmentacion"),
    CustomerCrmRoute(
        route_id="customers.territories", label="Territorios", group="Segmentación",
        tooltip="Territorios de venta.",
        required_permission=CRMPermissions.SEGMENTS_VIEW, capability="segmentacion"),
    CustomerCrmRoute(
        route_id="customers.portfolios", label="Carteras", group="Segmentación",
        tooltip="Carteras comerciales.",
        required_permission=CRMPermissions.SEGMENTS_VIEW, capability="segmentacion"),
    CustomerCrmRoute(
        route_id="customers.ownership", label="Propietarios", group="Segmentación",
        tooltip="Propietario/responsable por cliente.",
        required_permission=CRMPermissions.SEGMENTS_VIEW, capability="segmentacion"),

    # -- Comunicaciones ----------------------------------------------------------
    CustomerCrmRoute(
        route_id="customers.communication_preferences", label="Preferencias", group="Comunicaciones",
        tooltip="Preferencias de comunicación.",
        required_permission=CustomerPermissions.CONSENT_VIEW, capability="comunicaciones"),
    CustomerCrmRoute(
        route_id="customers.consents", label="Consentimientos", group="Comunicaciones",
        tooltip="Evidencia de consentimiento.",
        required_permission=CustomerPermissions.CONSENT_VIEW, capability="comunicaciones"),
    CustomerCrmRoute(
        route_id="customers.whatsapp_summary", label="WhatsApp", group="Comunicaciones",
        tooltip="Resumen de la integración con WhatsApp.",
        required_permission=CustomerPermissions.CONSENT_VIEW, capability="comunicaciones"),
    CustomerCrmRoute(
        route_id="customers.notification_history", label="Notificaciones", group="Comunicaciones",
        tooltip="Historial de notificaciones enviadas.",
        required_permission=CustomerPermissions.CONSENT_VIEW, capability="comunicaciones"),

    # -- Privacidad --------------------------------------------------------------
    CustomerCrmRoute(
        route_id="customers.privacy_requests", label="Solicitudes", group="Privacidad",
        tooltip="Solicitudes de privacidad (ARCO).",
        required_permission=CustomerPermissions.PRIVACY_REQUEST_VIEW, capability="privacidad"),
    CustomerCrmRoute(
        route_id="customers.retention", label="Retención", group="Privacidad",
        tooltip="Política de retención de datos.",
        required_permission=CustomerPermissions.PRIVACY_REQUEST_VIEW, capability="privacidad"),
    CustomerCrmRoute(
        route_id="customers.anonymization", label="Anonimización", group="Privacidad",
        tooltip="Anonimización de clientes.",
        required_permission=CustomerPermissions.PRIVACY_REQUEST_VIEW, capability="privacidad"),
    CustomerCrmRoute(
        route_id="customers.data_exports", label="Exportaciones", group="Privacidad",
        tooltip="Exportaciones de datos sensibles.",
        required_permission=CustomerPermissions.PRIVACY_REQUEST_VIEW, capability="privacidad"),

    # -- Control -------------------------------------------------------------
    CustomerCrmRoute(
        route_id="customers.data_quality", label="Calidad de datos", group="Control",
        tooltip="Incidencias de calidad de datos.",
        required_permission=CustomerPermissions.DATA_QUALITY_VIEW, capability="control"),
    CustomerCrmRoute(
        route_id="customers.imports", label="Importaciones", group="Control",
        tooltip="Lotes de importación.",
        required_permission=CustomerPermissions.DATA_QUALITY_VIEW, capability="control"),
    CustomerCrmRoute(
        route_id="customers.audit", label="Auditoría", group="Control",
        tooltip="Bitácora de auditoría del módulo.",
        required_permission=CustomerPermissions.DATA_QUALITY_VIEW, capability="control"),
    CustomerCrmRoute(
        route_id="customers.settings", label="Configuración", group="Control",
        tooltip="Configuración del módulo.",
        required_permission=CustomerPermissions.DATA_QUALITY_VIEW, capability="control"),
)


def visible_routes(capabilities: CustomerCrmCapabilities) -> tuple[CustomerCrmRoute, ...]:
    """Return routes authorized by UI capabilities, not raw route permissions."""
    if not capabilities.module_view:
        return ()
    return tuple(
        route for route in CUSTOMER_CRM_ROUTES
        if bool(getattr(capabilities, route.capability, False)))


def grouped_routes(
    routes: tuple[CustomerCrmRoute, ...] | list[CustomerCrmRoute] | None = None,
) -> list[tuple[str, list[CustomerCrmRoute]]]:
    groups: list[tuple[str, list[CustomerCrmRoute]]] = []
    for route in CUSTOMER_CRM_ROUTES if routes is None else routes:
        if not groups or groups[-1][0] != route.group:
            groups.append((route.group, []))
        groups[-1][1].append(route)
    return groups
