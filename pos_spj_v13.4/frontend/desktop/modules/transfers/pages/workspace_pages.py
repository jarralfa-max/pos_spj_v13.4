"""Thin page declarations sharing the canonical responsive workspace shell."""
from .base_page import TransferWorkspacePage
from .transfer_requests_page import TransferRequestsPage


def _page(name, page_id, title, subtitle, action_text="", cycle_actions=()):
    return type(name, (TransferWorkspacePage,), {
        "page_id": page_id, "title": title, "subtitle": subtitle,
        "action_text": action_text, "cycle_actions": cycle_actions, "__module__": __name__,
    })


# Integración Logística 32cfbf: cada etapa con su acción real.
PendingApprovalsPage = _page("PendingApprovalsPage", "transfers_approvals", "Aprobaciones", "Decisiones parciales y segregación de funciones.",
                             cycle_actions=(("Aprobar", "approve"), ("Rechazar", "reject")))
PickingPage = _page("PickingPage", "transfers_picking", "Picking", "Aprobadas por preparar: se reserva en Inventario y se surte lo reservado.",
                    cycle_actions=(("Preparar (reservar y surtir)", "prepare"),))
ReadyToDispatchPage = _page("ReadyToDispatchPage", "transfers_ready_to_dispatch", "Listas para despacho", "Embarques verificados y listos para liberar.",
                            cycle_actions=(("Despachar", "dispatch"),))
InTransitPage = _page("InTransitPage", "transfers_in_transit", "En tránsito", "Custodia, llegada esperada y cadena de frío.",
                      cycle_actions=(("Recibir", "receive"),))
ReceivingPage = _page("ReceivingPage", "transfers_receipts", "Recepciones", "Recepción total, parcial y acumulativa en el destino.",
                      cycle_actions=(("Recibir", "receive"),))
DifferencesPage = _page("DifferencesPage", "transfers_differences", "Diferencias", "Faltantes, sobrantes, peso, calidad y evidencias.")
ReturnsPage = _page("ReturnsPage", "transfers_returns", "Devoluciones", "Retornos al origen con custodia propia.")
SuggestionsPage = _page("SuggestionsPage", "transfers_suggestions", "Sugerencias", "Redistribución propuesta por demanda y disponibilidad.")
TraceabilityPage = _page("TraceabilityPage", "transfers_traceability", "Trazabilidad", "Documento, lotes, ubicaciones y cadena de custodia.")
AlertsPage = _page("AlertsPage", "transfers_alerts", "Alertas", "Atrasos, diferencias críticas y cadena de frío.")
AnalyticsPage = _page("AnalyticsPage", "transfers_analytics", "Análisis", "Indicadores logísticos calculados por QueryServices.")
AuditPage = _page("AuditPage", "transfers_audit", "Auditoría", "Registro inmutable de acciones y autorizaciones.")
SettingsPage = _page("SettingsPage", "transfers_settings", "Configuración", "Policies, tolerancias, offline y notificaciones.")

PAGE_CLASSES = {page.page_id: page for page in (
    TransferRequestsPage, PendingApprovalsPage, PickingPage, ReadyToDispatchPage,
    InTransitPage, ReceivingPage, DifferencesPage, ReturnsPage, SuggestionsPage,
    TraceabilityPage, AlertsPage, AnalyticsPage, AuditPage, SettingsPage,
)}
