"""Forecast accuracy metrics (§22, BI-10) — MAE, RMSE, MAPE, sMAPE, WAPE,
MASE, BIAS. Pure functions, `Decimal` in/out.

BI-6 found none of the 8 legacy engines compute WAPE, sMAPE, MASE, or BIAS —
the most complete (`DemandForecastEngine.evaluate_accuracy`) stops at
MAE/RMSE/MAPE. §22 explicitly requires "para series con cero utilizar
métricas compatibles" — MAPE and sMAPE are undefined (or degenerate) at a
zero actual, so they return `None` rather than raising or silently
producing a nonsense number when every actual is zero; WAPE and BIAS stay
well-defined as long as the totals aren't degenerate, so they're the metrics
to prefer for intermittent/near-zero series.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Sequence

from backend.domain.forecasting.exceptions import ForecastingDomainError


class MetricInputError(ForecastingDomainError):
    pass


def _check_pair(actual: Sequence[Decimal], forecast: Sequence[Decimal]) -> None:
    if not actual or not forecast:
        raise MetricInputError("actual and forecast must not be empty")
    if len(actual) != len(forecast):
        raise MetricInputError(
            f"actual and forecast must be the same length ({len(actual)} != {len(forecast)})"
        )


def mae(actual: Sequence[Decimal], forecast: Sequence[Decimal]) -> Decimal:
    _check_pair(actual, forecast)
    errors = [abs(a - f) for a, f in zip(actual, forecast)]
    return sum(errors, Decimal("0")) / Decimal(len(errors))


def rmse(actual: Sequence[Decimal], forecast: Sequence[Decimal]) -> Decimal:
    _check_pair(actual, forecast)
    squared = [(a - f) * (a - f) for a, f in zip(actual, forecast)]
    mean_squared = sum(squared, Decimal("0")) / Decimal(len(squared))
    return mean_squared.sqrt()


def mape(actual: Sequence[Decimal], forecast: Sequence[Decimal]) -> Decimal | None:
    _check_pair(actual, forecast)
    terms = [abs(a - f) / abs(a) for a, f in zip(actual, forecast) if a != 0]
    if not terms:
        return None
    return sum(terms, Decimal("0")) / Decimal(len(terms)) * Decimal("100")


def smape(actual: Sequence[Decimal], forecast: Sequence[Decimal]) -> Decimal | None:
    _check_pair(actual, forecast)
    terms = []
    for a, f in zip(actual, forecast):
        denom = abs(a) + abs(f)
        if denom == 0:
            continue
        terms.append(Decimal("2") * abs(a - f) / denom)
    if not terms:
        return None
    return sum(terms, Decimal("0")) / Decimal(len(terms)) * Decimal("100")


def wape(actual: Sequence[Decimal], forecast: Sequence[Decimal]) -> Decimal:
    _check_pair(actual, forecast)
    total_actual = sum((abs(a) for a in actual), Decimal("0"))
    if total_actual == 0:
        raise MetricInputError("wape is undefined when the sum of |actual| is 0")
    total_error = sum((abs(a - f) for a, f in zip(actual, forecast)), Decimal("0"))
    return total_error / total_actual * Decimal("100")


def bias(actual: Sequence[Decimal], forecast: Sequence[Decimal]) -> Decimal:
    """Mean signed error (forecast - actual). Positive => the model tends to
    over-forecast; negative => under-forecast."""
    _check_pair(actual, forecast)
    errors = [f - a for a, f in zip(actual, forecast)]
    return sum(errors, Decimal("0")) / Decimal(len(errors))


def mase(
    actual: Sequence[Decimal],
    forecast: Sequence[Decimal],
    training_history: Sequence[Decimal],
) -> Decimal | None:
    """Mean Absolute Scaled Error — scales MAE by the in-sample one-step
    naive MAE from `training_history` (the data the model was trained on,
    NOT the held-out test window). Returns `None` when the training history
    is a flat line (naive MAE of 0) — MASE is undefined there, not infinite."""
    _check_pair(actual, forecast)
    if len(training_history) < 2:
        raise MetricInputError("mase requires at least 2 points of training_history")
    naive_errors = [abs(training_history[i] - training_history[i - 1])
                     for i in range(1, len(training_history))]
    naive_mae = sum(naive_errors, Decimal("0")) / Decimal(len(naive_errors))
    if naive_mae == 0:
        return None
    return mae(actual, forecast) / naive_mae
