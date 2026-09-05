"""Domain exceptions for the forecasting bounded context."""

from __future__ import annotations


class ForecastingDomainError(Exception):
    """Base for forecasting rule violations."""


class InsufficientHistoryError(ForecastingDomainError):
    """A series has fewer observations than its model's minimum_history_days."""


class ForecastModelNotFoundError(ForecastingDomainError):
    pass


class ForecastModelNotApprovedError(ForecastingDomainError):
    """Raised when a forecast run is requested against a model that has not
    cleared backtesting/approval (§20-23: no model replaces the active
    champion without evidence)."""


class ForecastRunNotFoundError(ForecastingDomainError):
    pass


class TimeSeriesNotFoundError(ForecastingDomainError):
    pass
