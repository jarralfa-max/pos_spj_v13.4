"""Declarative, permission-aware internal navigation for Procesamiento Cárnico
(§10 of the refactor spec). Mirrors
frontend/desktop/modules/losses/navigation/losses_sidebar.py, plus a
`feature_flag` field so the "Sacrificio futuro" sections stay hidden until
`slaughter_features_enabled` is turned on for the branch (§37/§58).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

from backend.application.meat_processing.permissions import MeatProcessingPermissions

SLAUGHTER_FEATURE_FLAG = "slaughter_features_enabled"


@dataclass(frozen=True, slots=True)
class MeatProcessingNavEntry:
    page_id: str
    title: str
    icon: str
    permission: str
    tooltip: str
    badge_key: str | None = None
    feature_flag: str | None = None


MEAT_PROCESSING_NAV: tuple[MeatProcessingNavEntry, ...] = (
    MeatProcessingNavEntry("mp_overview", "Resumen", "dashboard",
                           MeatProcessingPermissions.DASHBOARD_VIEW,
                           "Indicadores operativos de procesamiento cárnico."),
    MeatProcessingNavEntry("mp_production_plan", "Plan de producción", "calendar",
                           MeatProcessingPermissions.PLAN_VIEW,
                           "Plan de producción operativo por periodo."),
    MeatProcessingNavEntry("mp_processing_orders", "Órdenes", "orders",
                           MeatProcessingPermissions.ORDER_VIEW,
                           "Órdenes de procesamiento y su ciclo de vida.",
                           badge_key="orders_needing_attention"),
    MeatProcessingNavEntry("mp_preparation", "Preparación", "checklist",
                           MeatProcessingPermissions.PREPARATION_VIEW,
                           "Requerimientos, reservas, recursos y operarios antes de liberar."),
    MeatProcessingNavEntry("mp_active_processing", "En proceso", "activity",
                           MeatProcessingPermissions.ACTIVE_PROCESSING_VIEW,
                           "Órdenes en ejecución en tiempo real.",
                           badge_key="active_orders"),
    MeatProcessingNavEntry("mp_weighings_consumptions", "Pesajes y consumos", "scale",
                           MeatProcessingPermissions.WEIGHT_VIEW,
                           "Entradas, pesajes intermedios y consumos capturados."),
    MeatProcessingNavEntry("mp_cutting", "Despiece", "cutting",
                           MeatProcessingPermissions.CUTTING_VIEW,
                           "Esquemas de despiece y outputs principales/coproductos."),
    MeatProcessingNavEntry("mp_derived_products", "Productos derivados", "derived",
                           MeatProcessingPermissions.DERIVED_PRODUCTS_VIEW,
                           "Molido, mezclado, marinado y formulación."),
    MeatProcessingNavEntry("mp_packaging_labeling", "Empaque y etiquetado", "package",
                           MeatProcessingPermissions.PACKAGING_LABELING_VIEW,
                           "Empaque, reempaque y etiquetas de trazabilidad."),
    MeatProcessingNavEntry("mp_produced_lots", "Lotes producidos", "lots",
                           MeatProcessingPermissions.PRODUCED_LOTS_VIEW,
                           "Lotes productivos generados y su estado."),
    MeatProcessingNavEntry("mp_yields", "Rendimientos", "yield",
                           MeatProcessingPermissions.YIELD_VIEW,
                           "Rendimiento esperado vs. real y conciliación.",
                           badge_key="yield_out_of_tolerance"),
    MeatProcessingNavEntry("mp_quality", "Calidad", "quality",
                           MeatProcessingPermissions.QUALITY_VIEW,
                           "Inspecciones, bloqueos y liberaciones de outputs.",
                           badge_key="pending_quality"),
    MeatProcessingNavEntry("mp_rework", "Reprocesos", "rework",
                           MeatProcessingPermissions.REWORK_VIEW,
                           "Órdenes de reproceso originadas en calidad o incidencias."),
    MeatProcessingNavEntry("mp_incidents", "Incidencias", "incident",
                           MeatProcessingPermissions.INCIDENTS_VIEW,
                           "Fallas de equipo, faltantes y desviaciones operativas.",
                           badge_key="open_incidents"),
    MeatProcessingNavEntry("mp_traceability", "Trazabilidad", "trace",
                           MeatProcessingPermissions.TRACEABILITY_VIEW,
                           "Genealogía de lotes: qué entró, qué salió, qué orden lo generó."),
    MeatProcessingNavEntry("mp_alerts", "Alertas", "bell",
                           MeatProcessingPermissions.ALERTS_VIEW,
                           "Excepciones críticas de producción.",
                           badge_key="critical_alerts"),
    MeatProcessingNavEntry("mp_analytics", "Análisis", "chart",
                           MeatProcessingPermissions.ANALYTICS_VIEW,
                           "Tendencias de producción, rendimiento y merma."),
    MeatProcessingNavEntry("mp_audit", "Auditoría", "audit",
                           MeatProcessingPermissions.AUDIT_VIEW,
                           "Trazabilidad inmutable de operaciones y autorizaciones."),
    MeatProcessingNavEntry("mp_settings", "Configuración", "settings",
                           MeatProcessingPermissions.SETTINGS_VIEW,
                           "Procesos, áreas, tolerancias, básculas y notificaciones."),

    # ── Sacrificio futuro (§37/§50) — mismo bounded context, feature-flagged ──
    MeatProcessingNavEntry("mp_animal_reception", "Recepción de animales", "receiving",
                           MeatProcessingPermissions.SLAUGHTER_ANIMAL_RECEPTION,
                           "Recepción y pesaje vivo de animales.",
                           feature_flag=SLAUGHTER_FEATURE_FLAG),
    MeatProcessingNavEntry("mp_animal_lots", "Lotes de animales", "animal_lot",
                           MeatProcessingPermissions.SLAUGHTER_ANIMAL_LOT_MANAGE,
                           "Lotes de animales recibidos.",
                           feature_flag=SLAUGHTER_FEATURE_FLAG),
    MeatProcessingNavEntry("mp_ante_mortem", "Ante mortem", "inspection",
                           MeatProcessingPermissions.SLAUGHTER_ANTE_MORTEM_RECORD,
                           "Inspección ante mortem.",
                           feature_flag=SLAUGHTER_FEATURE_FLAG),
    MeatProcessingNavEntry("mp_slaughter_orders", "Órdenes de sacrificio", "orders",
                           MeatProcessingPermissions.SLAUGHTER_ORDER_CREATE,
                           "Órdenes de sacrificio.",
                           feature_flag=SLAUGHTER_FEATURE_FLAG),
    MeatProcessingNavEntry("mp_slaughter_execution", "Faena", "activity",
                           MeatProcessingPermissions.SLAUGHTER_EXECUTE,
                           "Ejecución de faena: sangrado, escaldado, eviscerado.",
                           feature_flag=SLAUGHTER_FEATURE_FLAG),
    MeatProcessingNavEntry("mp_carcasses", "Canales", "carcass",
                           MeatProcessingPermissions.SLAUGHTER_CARCASS_CREATE,
                           "Canales generadas por faena.",
                           feature_flag=SLAUGHTER_FEATURE_FLAG),
    MeatProcessingNavEntry("mp_post_mortem", "Post mortem", "inspection",
                           MeatProcessingPermissions.SLAUGHTER_POST_MORTEM_RECORD,
                           "Inspección post mortem.",
                           feature_flag=SLAUGHTER_FEATURE_FLAG),
    MeatProcessingNavEntry("mp_chilling", "Enfriamiento", "cold",
                           MeatProcessingPermissions.SLAUGHTER_CHILLING_MANAGE,
                           "Cadena de frío de canales.",
                           feature_flag=SLAUGHTER_FEATURE_FLAG),
    MeatProcessingNavEntry("mp_carcass_classification", "Clasificación de canales", "grade",
                           MeatProcessingPermissions.SLAUGHTER_CARCASS_CLASSIFY,
                           "Clasificación de canales.",
                           feature_flag=SLAUGHTER_FEATURE_FLAG),
    MeatProcessingNavEntry("mp_condemnations", "Decomisos", "condemn",
                           MeatProcessingPermissions.SLAUGHTER_CONDEMNATION_RECORD,
                           "Decomisos registrados.",
                           feature_flag=SLAUGHTER_FEATURE_FLAG),
)


def visible_entries(
    has_permission: Callable[[str], bool],
    badges: Mapping[str, int] | None = None,
    has_feature: Callable[[str], bool] | None = None,
) -> tuple[tuple[MeatProcessingNavEntry, int | None], ...]:
    badges = badges or {}
    feature_enabled = has_feature or (lambda _flag: False)
    return tuple(
        (entry, badges.get(entry.badge_key) if entry.badge_key else None)
        for entry in MEAT_PROCESSING_NAV
        if has_permission(entry.permission)
        and (entry.feature_flag is None or feature_enabled(entry.feature_flag))
    )
