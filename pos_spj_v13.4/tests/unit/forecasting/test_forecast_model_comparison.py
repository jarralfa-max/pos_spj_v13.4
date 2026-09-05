from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from backend.domain.forecasting.value_objects.forecast_backtest import (
    ForecastAccuracyMetrics,
    ForecastBacktest,
)
from backend.domain.forecasting.value_objects.forecast_model_comparison import compare
from backend.shared.ids import new_uuid


def _backtest(model_key, version, wape) -> ForecastBacktest:
    return ForecastBacktest(
        id=new_uuid(), model_key=model_key, model_version=version,
        series_definition_key="daily_sales_by_product",
        train_from=date(2026, 7, 1), train_to=date(2026, 8, 31),
        test_from=date(2026, 9, 1), test_to=date(2026, 9, 7),
        metrics=ForecastAccuracyMetrics(
            mae=Decimal("1"), rmse=Decimal("1"), mape=None, smape=None,
            wape=wape, bias=Decimal("0"), mase=None,
        ),
        evaluated_at=datetime(2026, 9, 8, tzinfo=timezone.utc),
    )


def test_challenger_wins_when_metric_is_lower():
    champion = _backtest("ses", 1, Decimal("20"))
    challenger = _backtest("holt", 1, Decimal("8"))
    result = compare(champion, challenger, metric_key="wape")
    assert result.challenger_wins is True
    assert result.champion_value == Decimal("20")
    assert result.challenger_value == Decimal("8")


def test_champion_keeps_when_metric_is_not_better():
    champion = _backtest("ses", 1, Decimal("8"))
    challenger = _backtest("holt", 2, Decimal("20"))
    result = compare(champion, challenger, metric_key="wape")
    assert result.challenger_wins is False


def test_rejects_unsupported_metric_key():
    champion = _backtest("ses", 1, Decimal("8"))
    challenger = _backtest("holt", 2, Decimal("20"))
    with pytest.raises(ValueError):
        compare(champion, challenger, metric_key="mape")
