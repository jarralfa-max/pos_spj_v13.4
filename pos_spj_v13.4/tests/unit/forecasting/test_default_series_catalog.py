from backend.application.forecasting.services.default_series_catalog import (
    DAILY_SALES_BY_PRODUCT_KEY,
    build_default_series_catalog,
)


def test_default_catalog_registers_daily_sales_by_product():
    registry = build_default_series_catalog()
    series = registry.get(DAILY_SALES_BY_PRODUCT_KEY)
    assert series.dimension_keys == ("product", "branch")
    assert series.minimum_history_days == 14
