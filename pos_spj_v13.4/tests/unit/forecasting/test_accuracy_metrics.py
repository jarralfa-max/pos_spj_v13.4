from decimal import Decimal

import pytest

from backend.domain.forecasting.services import accuracy_metrics as am


def D(v):
    return Decimal(str(v))


def test_mae():
    actual = (D(10), D(20), D(30))
    forecast = (D(8), D(20), D(33))
    assert am.mae(actual, forecast) == Decimal(5) / Decimal(3)


def test_mae_rejects_mismatched_lengths():
    with pytest.raises(am.MetricInputError):
        am.mae((D(1), D(2)), (D(1),))


def test_mae_rejects_empty_input():
    with pytest.raises(am.MetricInputError):
        am.mae((), ())


def test_rmse():
    assert am.rmse((D(0),), (D(5),)) == D(5)


def test_mape_skips_zero_actual_points():
    actual = (D(10), D(0), D(20))
    forecast = (D(12), D(100), D(18))
    assert am.mape(actual, forecast) == D(15)


def test_mape_returns_none_when_all_actuals_are_zero():
    assert am.mape((D(0), D(0)), (D(1), D(2))) is None


def test_smape_max_case():
    assert am.smape((D(10),), (D(30),)) == D(100)


def test_smape_returns_none_when_actual_and_forecast_both_zero():
    assert am.smape((D(0),), (D(0),)) is None


def test_wape():
    actual = (D(10), D(20))
    forecast = (D(13), D(20))
    assert am.wape(actual, forecast) == D(10)


def test_wape_raises_when_sum_of_actual_is_zero():
    with pytest.raises(am.MetricInputError):
        am.wape((D(0), D(0)), (D(1), D(2)))


def test_bias_positive_means_over_forecasting():
    actual = (D(10), D(20))
    forecast = (D(15), D(18))
    assert am.bias(actual, forecast) == D("1.5")


def test_bias_negative_means_under_forecasting():
    actual = (D(20),)
    forecast = (D(10),)
    assert am.bias(actual, forecast) == D(-10)


def test_mase():
    actual = (D(10),)
    forecast = (D(15),)
    training_history = (D(0), D(5), D(10), D(15))
    assert am.mase(actual, forecast, training_history) == D(1)


def test_mase_returns_none_for_flat_training_history():
    training_history = (D(5), D(5), D(5))
    assert am.mase((D(10),), (D(15),), training_history) is None


def test_mase_requires_at_least_two_training_points():
    with pytest.raises(am.MetricInputError):
        am.mase((D(10),), (D(15),), (D(5),))


def test_perfect_forecast_yields_zero_error_metrics():
    actual = (D(10), D(20))
    forecast = (D(10), D(20))
    training_history = (D(5), D(10), D(15), D(20))
    assert am.mae(actual, forecast) == D(0)
    assert am.rmse(actual, forecast) == D(0)
    assert am.mape(actual, forecast) == D(0)
    assert am.smape(actual, forecast) == D(0)
    assert am.wape(actual, forecast) == D(0)
    assert am.bias(actual, forecast) == D(0)
    assert am.mase(actual, forecast, training_history) == D(0)
