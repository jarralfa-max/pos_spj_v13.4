from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from backend.domain.forecasting.value_objects.forecast_backtest import (
    ForecastAccuracyMetrics,
    ForecastBacktest,
)
from backend.shared.ids import new_uuid


def _metrics(**overrides) -> ForecastAccuracyMetrics:
    fields = dict(
        mae=Decimal("1"), rmse=Decimal("1"), mape=Decimal("10"),
        smape=Decimal("10"), wape=Decimal("10"), bias=Decimal("0.5"), mase=Decimal("1"),
    )
    fields.update(overrides)
    return ForecastAccuracyMetrics(**fields)


def _backtest(**overrides) -> ForecastBacktest:
    fields = dict(
        id=new_uuid(), model_key="ses_default", model_version=1,
        series_definition_key="daily_sales_by_product",
        train_from=date(2026, 7, 1), train_to=date(2026, 8, 31),
        test_from=date(2026, 9, 1), test_to=date(2026, 9, 7),
        metrics=_metrics(), evaluated_at=datetime(2026, 9, 8, tzinfo=timezone.utc),
    )
    fields.update(overrides)
    return ForecastBacktest(**fields)


def test_valid_backtest_constructs():
    backtest = _backtest()
    assert backtest.model_key == "ses_default"


def test_negative_mae_is_rejected():
    with pytest.raises(ValueError):
        _metrics(mae=Decimal("-1"))


def test_negative_mape_is_rejected_but_none_is_allowed():
    with pytest.raises(ValueError):
        _metrics(mape=Decimal("-1"))
    _metrics(mape=None)  # does not raise


def test_rejects_test_window_overlapping_or_before_training_window():
    with pytest.raises(ValueError):
        _backtest(test_from=date(2026, 8, 15))  # inside training window


def test_rejects_non_uuidv7_id():
    with pytest.raises(ValueError):
        _backtest(id="not-a-uuid")


def test_rejects_version_below_one():
    with pytest.raises(ValueError):
        _backtest(model_version=0)
