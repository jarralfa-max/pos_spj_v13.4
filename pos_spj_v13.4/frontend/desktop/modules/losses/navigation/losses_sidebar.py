"""Declarative, permission-aware internal navigation for Mermas."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

from backend.application.losses.permissions import LossPermissions


@dataclass(frozen=True, slots=True)
class LossNavEntry:
    page_id: str
    title: str
    icon: str
    permission: str
    tooltip: str
    badge_key: str | None = None


LOSSES_NAV: tuple[LossNavEntry, ...] = (
    LossNavEntry("losses_overview", "Resumen", "dashboard", LossPermissions.OVERVIEW_VIEW, "Indicadores operativos y económicos de pérdidas."),
    LossNavEntry("losses_registration", "Registro", "add", LossPermissions.REGISTRATION_VIEW, "Registrar y documentar una pérdida."),
    LossNavEntry("losses_pending", "Pendientes", "pending", LossPermissions.PENDING_VIEW, "Expedientes que requieren revisión o aprobación.", "pending_review"),
    LossNavEntry("losses_production", "Producción", "production", LossPermissions.PRODUCTION_VIEW, "Pérdidas originadas en procesos productivos."),
    LossNavEntry("losses_inventory", "Inventario", "inventory", LossPermissions.INVENTORY_VIEW, "Pérdidas y diferencias originadas en inventario."),
    LossNavEntry("losses_expiry_damage", "Caducidad y daño", "expiry", LossPermissions.EXPIRY_DAMAGE_VIEW, "Caducidad, deterioro y daño operativo."),
    LossNavEntry("losses_quality", "Calidad y decomisos", "quality", LossPermissions.QUALITY_VIEW, "Rechazos, contaminación y decomisos."),
    LossNavEntry("losses_yields", "Rendimientos", "yield", LossPermissions.YIELD_VIEW, "Variaciones contra rendimientos esperados."),
    LossNavEntry("losses_recovery", "Recuperación", "recovery", LossPermissions.RECOVERY_VIEW, "Reproceso, reclasificación y valor recuperado."),
    LossNavEntry("losses_disposition", "Disposición", "disposal", LossPermissions.DISPOSITION_VIEW, "Tratamiento y disposición final autorizada."),
    LossNavEntry("losses_investigations", "Investigaciones", "investigation", LossPermissions.INVESTIGATION_VIEW, "Investigaciones y causa raíz abiertas.", "open_investigations"),
    LossNavEntry("losses_corrective_actions", "Acciones correctivas", "tasks", LossPermissions.CORRECTIVE_ACTION_VIEW, "Acciones, responsables y verificación.", "overdue_actions"),
    LossNavEntry("losses_alerts", "Alertas", "bell", LossPermissions.ALERT_VIEW, "Excepciones críticas y reincidencias.", "critical_alerts"),
    LossNavEntry("losses_analysis", "Análisis", "chart", LossPermissions.ANALYTICS_VIEW, "Tendencias, Pareto y análisis comparativo."),
    LossNavEntry("losses_audit", "Auditoría", "audit", LossPermissions.VIEW_AUDIT, "Trazabilidad inmutable de expedientes y decisiones."),
    LossNavEntry("losses_settings", "Configuración", "settings", LossPermissions.SETTINGS_VIEW, "Clasificaciones, causas, límites y notificaciones."),
)


def visible_entries(
    has_permission: Callable[[str], bool],
    badges: Mapping[str, int] | None = None,
) -> tuple[tuple[LossNavEntry, int | None], ...]:
    badges = badges or {}
    return tuple(
        (entry, badges.get(entry.badge_key) if entry.badge_key else None)
        for entry in LOSSES_NAV
        if has_permission(entry.permission)
    )
