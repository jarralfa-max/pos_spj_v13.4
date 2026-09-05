"""Domain exceptions for the analytical_alerting bounded context."""

from __future__ import annotations


class AnalyticalAlertingDomainError(Exception):
    """Base for analytical_alerting rule violations."""


class InvalidAlertTransitionError(AnalyticalAlertingDomainError):
    pass
