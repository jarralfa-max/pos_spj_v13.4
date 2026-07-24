"""Declarative internal sidebar for the one global Transferencias entry.

This is presentation data only.  The app shell renders it with the SPJ
ModuleSidebar and asks the query service for badges; it contains no Qt, SQL,
repository, inventory, or permission decision logic.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

from backend.application.transfers.permissions import TransferPermissions


@dataclass(frozen=True, slots=True)
class TransferNavEntry:
    page_id: str
    title: str
    icon: str
    permission: str
    tooltip: str
    badge_key: str | None = None


TRANSFERS_NAV: tuple[TransferNavEntry, ...] = (
    TransferNavEntry("transfers_overview", "Resumen", "dashboard", TransferPermissions.DASHBOARD_VIEW, "Estado operativo de transferencias."),
    TransferNavEntry("transfers_requests", "Solicitudes", "request", TransferPermissions.REQUEST_VIEW, "Solicitudes de traslado pendientes.", "pending_requests"),
    TransferNavEntry("transfers_approvals", "Aprobaciones", "approval", TransferPermissions.APPROVE, "Solicitudes que requieren aprobación.", "pending_approvals"),
    TransferNavEntry("transfers_picking", "Picking", "picking", TransferPermissions.PICK, "Preparación, lotes y ubicaciones de origen."),
    TransferNavEntry("transfers_ready_to_dispatch", "Listas para despacho", "dispatch", TransferPermissions.DISPATCH_VIEW, "Transferencias preparadas para salida.", "ready_to_dispatch"),
    TransferNavEntry("transfers_in_transit", "En tránsito", "transit", TransferPermissions.DISPATCH_VIEW, "Mercancía bajo custodia en tránsito.", "in_transit"),
    TransferNavEntry("transfers_receipts", "Recepciones", "receipt", TransferPermissions.RECEIVE_VIEW, "Recepciones pendientes y confirmadas.", "pending_receipts"),
    TransferNavEntry("transfers_differences", "Diferencias", "difference", TransferPermissions.DIFFERENCE_VIEW, "Diferencias de cantidad, peso, calidad o custodia.", "open_differences"),
    TransferNavEntry("transfers_returns", "Devoluciones", "return", TransferPermissions.RETURN_CREATE, "Devoluciones al origen y sus recepciones."),
    TransferNavEntry("transfers_suggestions", "Sugerencias", "suggestion", TransferPermissions.REQUEST_VIEW, "Redistribución propuesta; no mueve inventario."),
    TransferNavEntry("transfers_traceability", "Trazabilidad", "traceability", TransferPermissions.AUDIT_VIEW, "Custodia, lotes y ruta logística."),
    TransferNavEntry("transfers_alerts", "Alertas", "bell", TransferPermissions.DASHBOARD_VIEW, "Excepciones, atrasos y cadena de frío."),
    TransferNavEntry("transfers_analytics", "Análisis", "chart", TransferPermissions.EXPORT, "Indicadores y exportación logística."),
    TransferNavEntry("transfers_audit", "Auditoría", "audit", TransferPermissions.AUDIT_VIEW, "Bitácora inmutable de operaciones."),
    TransferNavEntry("transfers_settings", "Configuración", "settings", TransferPermissions.SETTINGS_VIEW, "Políticas, tolerancias y notificaciones."),
)


def visible_entries(has_permission: Callable[[str], bool], badges: Mapping[str, int] | None = None) -> tuple[tuple[TransferNavEntry, int | None], ...]:
    """Return only permitted entries and server-calculated optional badge counts."""
    badges = badges or {}
    return tuple((entry, badges.get(entry.badge_key) if entry.badge_key else None)
                 for entry in TRANSFERS_NAV if has_permission(entry.permission))
