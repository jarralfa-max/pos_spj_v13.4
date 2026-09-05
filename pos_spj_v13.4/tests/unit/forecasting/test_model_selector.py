from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from backend.domain.forecasting.services.model_selector import (
    NoComparableBacktestsError,
    select_best_model,
)
from backend.domain.forecasting.value_objects.forecast_backtest import (
    ForecastAccuracyMetrics,
    ForecastBacktest,
)
from backend.shared.ids import new_uuid


def _backtest(model_key, wape) -> ForecastBacktest:
    return ForecastBacktest(
        id=new_uuid(), model_key=model_key, model_version=1,
        series_definition_key="daily_sales_by_product",
        train_from=date(2026, 7, 1), train_to=date(2026, 8, 31),
        test_from=date(2026, 9, 1), test_to=date(2026, 9, 7),
        metrics=ForecastAccuracyMetrics(
            mae=Decimal("1"), rmse=Decimal("1"), mape=None, smape=None,
            wape=wape, bias=Decimal("0"), mase=None,
        ),
        evaluated_at=datetime(2026, 9, 8, tzinfo=timezone.utc),
    )


def test_selects_lowest_wape():
    candidates = [_backtest("ses", Decimal("20")), _backtest("holt", Decimal("8")),
                  _backtest("naive", Decimal("35"))]
    winner = select_best_model(candidates, metric_key="wape")
    assert winner.model_key == "holt"


def test_raises_on_empty_input():
    with pytest.raises(NoComparableBacktestsError):
        select_best_model([])


def test_rejects_unsupported_metric_key():
    with pytest.raises(ValueError):
        select_best_model([_backtest("ses", Decimal("10"))], metric_key="mape")
