"""Granular Business Intelligence / Analytics / Forecasting / Decision
Intelligence permission codes (master-prompt §104-114, BI-2).

Reuses the existing canonical module key ``INTELIGENCIA_BI`` — the sidebar
button ("Inteligencia de Negocios", `interfaz/menu_lateral.py`) and the
existing flat action codes (`ver`, `ver_ventas`, `ver_inventario`, …,
`configurar`) already point at it, and `security/rbac.py` seeds those flat
codes to default roles. Introducing a parallel module key would violate the
"una sola ruta canónica" principle (§3/§64 of the refactor master prompt) —
see `docs/refactor/BI-2_security.md`.

The flat legacy codes are intentionally **not** duplicated here (they stay as
raw strings in `backend/application/services/bi_dashboard_service.py` until
BI-4 relocates that service); this class only adds the new granular surface
needed for forecasting, decision intelligence, scenarios and alerts, which
had no permission codes at all before BI-2.

Codes use the app-wide canonical `MODULO.accion` format (see
`core/security/permission_catalog.py`); comparisons are case-insensitive.
"""

from __future__ import annotations


class AnalyticsPermissions:
    # ── general (§104) ───────────────────────────────────────────────────
    ACCESS = "INTELIGENCIA_BI.acceso"
    DASHBOARD_VIEW = "INTELIGENCIA_BI.dashboard.ver"
    GLOBAL_SEARCH = "INTELIGENCIA_BI.busqueda_global"
    AUDIT_VIEW = "INTELIGENCIA_BI.auditoria.ver"
    SETTINGS_VIEW = "INTELIGENCIA_BI.configuracion.ver"
    SETTINGS_MANAGE = "INTELIGENCIA_BI.configuracion.editar"
    #: BI-30 — reuses the legacy flat code already registered in
    #: `permission_catalog.py` (`"exportar"`), not a new one (§3/§64).
    REPORTS_EXPORT = "INTELIGENCIA_BI.exportar"

    # ── ventas (§105) ────────────────────────────────────────────────────
    SALES_VIEW = "INTELIGENCIA_BI.ventas.ver"
    SALES_DETAIL_VIEW = "INTELIGENCIA_BI.ventas.detalle.ver"
    SALES_MARGIN_VIEW = "INTELIGENCIA_BI.ventas.margen.ver"
    SALES_EXPORT = "INTELIGENCIA_BI.ventas.exportar"

    # ── inventario (§106) ────────────────────────────────────────────────
    INVENTORY_VIEW = "INTELIGENCIA_BI.inventario.ver"
    INVENTORY_VALUE_VIEW = "INTELIGENCIA_BI.inventario.valor.ver"
    INVENTORY_RISK_VIEW = "INTELIGENCIA_BI.inventario.riesgo.ver"
    INVENTORY_FORECAST_VIEW = "INTELIGENCIA_BI.inventario.forecast.ver"

    # ── compras (§107) ───────────────────────────────────────────────────
    PURCHASES_VIEW = "INTELIGENCIA_BI.compras.ver"
    PURCHASE_COST_VIEW = "INTELIGENCIA_BI.compras.costo.ver"
    PURCHASE_FORECAST_VIEW = "INTELIGENCIA_BI.compras.forecast.ver"
    PURCHASE_RECOMMENDATION_VIEW = "INTELIGENCIA_BI.compras.recomendacion.ver"

    # ── producción (§108) ────────────────────────────────────────────────
    PRODUCTION_VIEW = "INTELIGENCIA_BI.produccion.ver"
    PRODUCTION_YIELD_VIEW = "INTELIGENCIA_BI.produccion.rendimiento.ver"
    PRODUCTION_FORECAST_VIEW = "INTELIGENCIA_BI.produccion.forecast.ver"
    PRODUCTION_RECOMMENDATION_VIEW = "INTELIGENCIA_BI.produccion.recomendacion.ver"

    # ── pricing (§109) ───────────────────────────────────────────────────
    PRICING_VIEW = "INTELIGENCIA_BI.pricing.ver"
    PRICING_MARGIN_VIEW = "INTELIGENCIA_BI.pricing.margen.ver"
    PRICING_ELASTICITY_VIEW = "INTELIGENCIA_BI.pricing.elasticidad.ver"
    PRICING_RECOMMENDATION_VIEW = "INTELIGENCIA_BI.pricing.recomendacion.ver"
    PRICING_SCENARIO_VIEW = "INTELIGENCIA_BI.pricing.escenario.ver"

    # ── finanzas (§110) ──────────────────────────────────────────────────
    FINANCE_VIEW = "INTELIGENCIA_BI.finanzas.ver"
    FINANCE_PROFITABILITY_VIEW = "INTELIGENCIA_BI.finanzas.rentabilidad.ver"
    FINANCE_CASHFLOW_VIEW = "INTELIGENCIA_BI.finanzas.flujo_caja.ver"
    FINANCE_SENSITIVE_VIEW = "INTELIGENCIA_BI.finanzas.sensible.ver"

    # ── forecast (§111) ──────────────────────────────────────────────────
    FORECAST_VIEW = "INTELIGENCIA_BI.forecast.ver"
    FORECAST_DEMAND_VIEW = "INTELIGENCIA_BI.forecast.demanda.ver"
    FORECAST_SALES_VIEW = "INTELIGENCIA_BI.forecast.ventas.ver"
    FORECAST_INVENTORY_VIEW = "INTELIGENCIA_BI.forecast.inventario.ver"
    FORECAST_PURCHASES_VIEW = "INTELIGENCIA_BI.forecast.compras.ver"
    FORECAST_PRODUCTION_VIEW = "INTELIGENCIA_BI.forecast.produccion.ver"
    FORECAST_BRANCHES_VIEW = "INTELIGENCIA_BI.forecast.sucursales.ver"
    FORECAST_MODEL_VIEW = "INTELIGENCIA_BI.forecast.modelo.ver"
    FORECAST_MODEL_CREATE = "INTELIGENCIA_BI.forecast.modelo.crear"
    FORECAST_MODEL_TEST = "INTELIGENCIA_BI.forecast.modelo.probar"
    FORECAST_MODEL_APPROVE = "INTELIGENCIA_BI.forecast.modelo.aprobar"
    FORECAST_MODEL_ACTIVATE = "INTELIGENCIA_BI.forecast.modelo.activar"
    FORECAST_MODEL_RETIRE = "INTELIGENCIA_BI.forecast.modelo.retirar"

    # ── decision intelligence (§112) ─────────────────────────────────────
    RECOMMENDATIONS_VIEW = "INTELIGENCIA_BI.recomendacion.ver"
    RECOMMENDATIONS_ACKNOWLEDGE = "INTELIGENCIA_BI.recomendacion.reconocer"
    RECOMMENDATIONS_APPROVE = "INTELIGENCIA_BI.recomendacion.aprobar"
    RECOMMENDATIONS_REJECT = "INTELIGENCIA_BI.recomendacion.rechazar"
    RECOMMENDATIONS_DISMISS = "INTELIGENCIA_BI.recomendacion.descartar"
    SCENARIOS_VIEW = "INTELIGENCIA_BI.escenario.ver"
    SCENARIOS_CREATE = "INTELIGENCIA_BI.escenario.crear"
    SCENARIOS_SHARE = "INTELIGENCIA_BI.escenario.compartir"
    SCENARIOS_DELETE = "INTELIGENCIA_BI.escenario.eliminar"

    # ── alertas (§113) ───────────────────────────────────────────────────
    ALERTS_VIEW = "INTELIGENCIA_BI.alerta.ver"
    ALERTS_ACKNOWLEDGE = "INTELIGENCIA_BI.alerta.reconocer"
    ALERTS_RESOLVE = "INTELIGENCIA_BI.alerta.resolver"
    ALERTS_DISMISS = "INTELIGENCIA_BI.alerta.descartar"
    ALERT_RULES_VIEW = "INTELIGENCIA_BI.alerta_regla.ver"
    ALERT_RULES_CREATE = "INTELIGENCIA_BI.alerta_regla.crear"
    ALERT_RULES_EDIT = "INTELIGENCIA_BI.alerta_regla.editar"
    ALERT_RULES_ACTIVATE = "INTELIGENCIA_BI.alerta_regla.activar"
    ALERT_SUBSCRIPTIONS_MANAGE = "INTELIGENCIA_BI.alerta_suscripcion.gestionar"

    # ── web remota futura (§114) ─────────────────────────────────────────
    REMOTE_ACCESS = "INTELIGENCIA_BI.remoto.acceso"
    REMOTE_EXECUTIVE_VIEW = "INTELIGENCIA_BI.remoto.ejecutivo.ver"
    REMOTE_BRANCH_VIEW = "INTELIGENCIA_BI.remoto.sucursal.ver"
    REMOTE_FORECAST_VIEW = "INTELIGENCIA_BI.remoto.forecast.ver"
    REMOTE_ALERTS_VIEW = "INTELIGENCIA_BI.remoto.alertas.ver"
    REMOTE_RECOMMENDATIONS_VIEW = "INTELIGENCIA_BI.remoto.recomendaciones.ver"


ALL_ANALYTICS_PERMISSIONS = frozenset(
    v for k, v in vars(AnalyticsPermissions).items()
    if not k.startswith("_") and isinstance(v, str)
)
