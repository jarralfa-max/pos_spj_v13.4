"""Default MetricDefinition catalog (BI-3).

Formulas mirror what `docs/architecture/BI_DASHBOARD.md` already documents as
implemented in `Bi*QueryService` (§40 of the master prompt: existing
formulas, not invented ones) plus two forward-looking metrics
(`CUSTOMER_FREQUENCY`, `FORECAST_ERROR`) explicitly named in §11 whose
computation lands in later phases (BI-12 Customer Analytics, BI-10
backtesting) — defining the metric's shape now is what lets those phases
plug in without inventing a formula ad hoc.
"""

from __future__ import annotations

from backend.application.analytics.permissions import AnalyticsPermissions
from backend.application.analytics.services.metric_registry import MetricRegistry
from backend.domain.analytics.enums import (
    AggregationType,
    CurrencyBehavior,
    FreshnessPolicy,
    ScopePolicy,
    TimeGrain,
)
from backend.domain.analytics.value_objects.metric_definition import MetricDefinition

_SALES_DIMENSIONS = ("branch", "category", "product", "channel", "payment_method")


def build_default_catalog() -> MetricRegistry:
    registry = MetricRegistry()
    for definition in _DEFAULT_METRICS:
        registry.register(definition)
    return registry


_DEFAULT_METRICS: tuple[MetricDefinition, ...] = (
    MetricDefinition(
        key="NET_SALES",
        name="Ventas netas",
        description="Suma de ventas completadas en el período.",
        domain_owner="sales",
        formula="SUM(ventas.total) WHERE estado = 'completada'",
        unit="MXN",
        aggregation=AggregationType.SUM,
        dimensions=_SALES_DIMENSIONS,
        time_grain=TimeGrain.DAILY,
        currency_behavior=CurrencyBehavior.MONETARY,
        permission=AnalyticsPermissions.SALES_VIEW,
        scope_policy=ScopePolicy.BRANCH,
        freshness_policy=FreshnessPolicy.NEAR_REAL_TIME,
    ),
    MetricDefinition(
        key="COGS",
        name="Costo de ventas",
        description=(
            "Costo real por línea vendida (detalles_venta.costo_unitario_real), "
            "con fallback a costo/precio_compra/costo_promedio del producto."
        ),
        domain_owner="sales",
        formula="SUM(detalles_venta.costo_unitario_real * cantidad) [fallback: producto.costo]",
        unit="MXN",
        aggregation=AggregationType.SUM,
        dimensions=_SALES_DIMENSIONS,
        time_grain=TimeGrain.DAILY,
        currency_behavior=CurrencyBehavior.MONETARY,
        permission=AnalyticsPermissions.SALES_MARGIN_VIEW,
        scope_policy=ScopePolicy.BRANCH,
        freshness_policy=FreshnessPolicy.NEAR_REAL_TIME,
    ),
    MetricDefinition(
        key="NET_PROFIT",
        name="Utilidad neta",
        description="Ventas netas menos costo de ventas menos gastos operativos.",
        domain_owner="finance",
        formula="NET_SALES - COGS - gastos",
        unit="MXN",
        aggregation=AggregationType.CUSTOM,
        dimensions=("branch",),
        time_grain=TimeGrain.DAILY,
        currency_behavior=CurrencyBehavior.MONETARY,
        permission=AnalyticsPermissions.FINANCE_PROFITABILITY_VIEW,
        scope_policy=ScopePolicy.BRANCH,
        freshness_policy=FreshnessPolicy.DAILY,
    ),
    MetricDefinition(
        key="GROSS_MARGIN_PCT",
        name="Margen %",
        description="Utilidad neta como porcentaje de las ventas netas.",
        domain_owner="finance",
        formula="NET_PROFIT / NET_SALES * 100",
        unit="%",
        aggregation=AggregationType.RATIO,
        dimensions=("branch", "category"),
        time_grain=TimeGrain.DAILY,
        currency_behavior=CurrencyBehavior.PERCENTAGE,
        permission=AnalyticsPermissions.FINANCE_PROFITABILITY_VIEW,
        scope_policy=ScopePolicy.BRANCH,
        freshness_policy=FreshnessPolicy.DAILY,
    ),
    MetricDefinition(
        key="AVERAGE_TICKET",
        name="Ticket promedio",
        description="Ventas netas entre número de órdenes completadas.",
        domain_owner="sales",
        formula="NET_SALES / ORDERS_COUNT",
        unit="MXN",
        aggregation=AggregationType.RATIO,
        dimensions=("branch",),
        time_grain=TimeGrain.DAILY,
        currency_behavior=CurrencyBehavior.MONETARY,
        permission=AnalyticsPermissions.SALES_VIEW,
        scope_policy=ScopePolicy.BRANCH,
        freshness_policy=FreshnessPolicy.NEAR_REAL_TIME,
    ),
    MetricDefinition(
        key="ORDERS_COUNT",
        name="Órdenes",
        description="Número de ventas completadas en el período.",
        domain_owner="sales",
        formula="COUNT(ventas) WHERE estado = 'completada'",
        unit="count",
        aggregation=AggregationType.COUNT,
        dimensions=("branch", "channel"),
        time_grain=TimeGrain.DAILY,
        currency_behavior=CurrencyBehavior.NONE,
        permission=AnalyticsPermissions.SALES_VIEW,
        scope_policy=ScopePolicy.BRANCH,
        freshness_policy=FreshnessPolicy.NEAR_REAL_TIME,
    ),
    MetricDefinition(
        key="INVENTORY_VALUE",
        name="Inventario valorizado",
        description="Valor del inventario a costo actual.",
        domain_owner="inventory",
        formula="SUM(inventory_stock.quantity * costo_producto)",
        unit="MXN",
        aggregation=AggregationType.SUM,
        dimensions=("branch", "category", "product"),
        time_grain=TimeGrain.DAILY,
        currency_behavior=CurrencyBehavior.MONETARY,
        permission=AnalyticsPermissions.INVENTORY_VALUE_VIEW,
        scope_policy=ScopePolicy.BRANCH,
        freshness_policy=FreshnessPolicy.DAILY,
    ),
    MetricDefinition(
        key="INVENTORY_TURNOVER",
        name="Rotación de inventario",
        description="Costo de ventas entre inventario valorizado.",
        domain_owner="inventory",
        formula="COGS / INVENTORY_VALUE",
        unit="ratio",
        aggregation=AggregationType.RATIO,
        dimensions=("branch", "category"),
        time_grain=TimeGrain.MONTHLY,
        currency_behavior=CurrencyBehavior.NONE,
        permission=AnalyticsPermissions.INVENTORY_VIEW,
        scope_policy=ScopePolicy.BRANCH,
        freshness_policy=FreshnessPolicy.DAILY,
    ),
    MetricDefinition(
        key="WASTE_RATE",
        name="Merma %",
        description="Valor de merma como porcentaje de las ventas netas.",
        domain_owner="losses",
        formula="merma_valor / NET_SALES * 100",
        unit="%",
        aggregation=AggregationType.RATIO,
        dimensions=("branch", "category"),
        time_grain=TimeGrain.DAILY,
        currency_behavior=CurrencyBehavior.PERCENTAGE,
        permission=AnalyticsPermissions.INVENTORY_VIEW,
        scope_policy=ScopePolicy.BRANCH,
        freshness_policy=FreshnessPolicy.DAILY,
    ),
    MetricDefinition(
        key="ACCOUNTS_RECEIVABLE",
        name="Cuentas por cobrar",
        description="Saldo positivo de cuentas por cobrar.",
        domain_owner="finance",
        formula="SUM(accounts_receivable.balance) WHERE balance > 0",
        unit="MXN",
        aggregation=AggregationType.SUM,
        dimensions=("branch", "customer"),
        time_grain=TimeGrain.DAILY,
        currency_behavior=CurrencyBehavior.MONETARY,
        permission=AnalyticsPermissions.FINANCE_SENSITIVE_VIEW,
        scope_policy=ScopePolicy.COMPANY,
        freshness_policy=FreshnessPolicy.NEAR_REAL_TIME,
    ),
    MetricDefinition(
        key="ACCOUNTS_PAYABLE",
        name="Cuentas por pagar",
        description="Saldo positivo de cuentas por pagar.",
        domain_owner="finance",
        formula="SUM(accounts_payable.balance) WHERE balance > 0",
        unit="MXN",
        aggregation=AggregationType.SUM,
        dimensions=("branch", "supplier"),
        time_grain=TimeGrain.DAILY,
        currency_behavior=CurrencyBehavior.MONETARY,
        permission=AnalyticsPermissions.FINANCE_SENSITIVE_VIEW,
        scope_policy=ScopePolicy.COMPANY,
        freshness_policy=FreshnessPolicy.NEAR_REAL_TIME,
    ),
    MetricDefinition(
        key="CUSTOMER_FREQUENCY",
        name="Frecuencia de cliente",
        description=(
            "Órdenes por cliente distinto en el período — forward-looking (§79/§11), "
            "computación real llega con Customer Analytics (BI-12)."
        ),
        domain_owner="customers",
        formula="ORDERS_COUNT / COUNT(DISTINCT cliente_id)",
        unit="ratio",
        aggregation=AggregationType.RATIO,
        dimensions=("customer_segment", "branch"),
        time_grain=TimeGrain.MONTHLY,
        currency_behavior=CurrencyBehavior.NONE,
        permission=AnalyticsPermissions.PURCHASES_VIEW,  # placeholder until BI-12 defines its own
        scope_policy=ScopePolicy.COMPANY,
        freshness_policy=FreshnessPolicy.STALE,
    ),
    MetricDefinition(
        key="FORECAST_ERROR",
        name="Error de pronóstico (WAPE)",
        description=(
            "Weighted Absolute Percentage Error del forecast activo vs. lo real — "
            "forward-looking (§68/§70/§11), computación real llega con Backtesting "
            "(BI-10)."
        ),
        domain_owner="forecasting",
        formula="SUM(ABS(forecast - actual)) / SUM(actual) * 100",
        unit="%",
        aggregation=AggregationType.RATIO,
        dimensions=("product", "branch"),
        time_grain=TimeGrain.DAILY,
        currency_behavior=CurrencyBehavior.PERCENTAGE,
        permission=AnalyticsPermissions.FORECAST_VIEW,
        scope_policy=ScopePolicy.BRANCH,
        freshness_policy=FreshnessPolicy.STALE,
    ),
)
