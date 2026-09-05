from datetime import date
from decimal import Decimal

import pytest

from backend.domain.analytics.enums import TimeGrain
from backend.domain.forecasting.value_objects.time_series import (
    TimeSeriesDefinition,
    TimeSeriesObservation,
)


def test_valid_time_series_definition_constructs():
    definition = TimeSeriesDefinition(
        key="daily_sales_by_product",
        name="Ventas diarias por producto",
        dimension_keys=("product", "branch"),
        time_grain=TimeGrain.DAILY,
        value_unit="kg",
        minimum_history_days=14,
    )
    assert definition.key == "daily_sales_by_product"


def test_rejects_unknown_dimension_key():
    with pytest.raises(ValueError):
        TimeSeriesDefinition(
            key="x", name="X", dimension_keys=("not_a_real_dimension",),
            time_grain=TimeGrain.DAILY, value_unit="kg", minimum_history_days=14,
        )


def test_rejects_non_positive_minimum_history_days():
    with pytest.raises(ValueError):
        TimeSeriesDefinition(
            key="x", name="X", dimension_keys=(), time_grain=TimeGrain.DAILY,
            value_unit="kg", minimum_history_days=0,
        )


def test_real_observation_does_not_require_imputation_reason():
    obs = TimeSeriesObservation(timestamp=date(2026, 9, 1), value=Decimal("10"))
    assert obs.is_imputed is False


def test_imputed_observation_requires_reason():
    """§18: a stockout day must never silently become a zero-demand
    observation — it must be an explicit, reasoned imputation."""
    with pytest.raises(ValueError):
        TimeSeriesObservation(timestamp=date(2026, 9, 1), value=Decimal("0"), is_imputed=True)

    obs = TimeSeriesObservation(
        timestamp=date(2026, 9, 1), value=Decimal("0"),
        is_imputed=True, imputation_reason="stockout",
    )
    assert obs.imputation_reason == "stockout"


def test_reason_without_imputed_flag_is_rejected():
    with pytest.raises(ValueError):
        TimeSeriesObservation(
            timestamp=date(2026, 9, 1), value=Decimal("10"),
            is_imputed=False, imputation_reason="stockout",
        )


def test_rejects_non_decimal_value():
    with pytest.raises(TypeError):
        TimeSeriesObservation(timestamp=date(2026, 9, 1), value=10.0)
