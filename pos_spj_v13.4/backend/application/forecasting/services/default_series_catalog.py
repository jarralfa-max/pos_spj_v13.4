"""Default TimeSeriesDefinition catalog (BI-8).

Starts with exactly one series — the one BI-9's baseline models and BI-12's
demand planning actually need first (daily product demand, optionally
scoped to a branch). §17 lists 7 possible dimensions; more series
(by-category, by-channel, by-supplier, ...) are added when a real consumer
needs them, not speculatively — same discipline BI-3 applied to the metric
catalog.
"""

from __future__ import annotations

from backend.application.forecasting.services.time_series_registry import TimeSeriesRegistry
from backend.domain.analytics.enums import TimeGrain
from backend.domain.forecasting.value_objects.time_series import TimeSeriesDefinition

DAILY_SALES_BY_PRODUCT_KEY = "daily_sales_by_product"


def build_default_series_catalog() -> TimeSeriesRegistry:
    registry = TimeSeriesRegistry()
    registry.register(_DAILY_SALES_BY_PRODUCT)
    return registry


_DAILY_SALES_BY_PRODUCT = TimeSeriesDefinition(
    key=DAILY_SALES_BY_PRODUCT_KEY,
    name="Ventas diarias por producto",
    description=(
        "Unidades vendidas por día para un producto, opcionalmente filtrado "
        "por sucursal. Fuente: detalles_venta/ventas (mismas tablas que "
        "BiSalesQueryService, BI-4)."
    ),
    dimension_keys=("product", "branch"),
    time_grain=TimeGrain.DAILY,
    value_unit="unidades",
    minimum_history_days=14,
)
