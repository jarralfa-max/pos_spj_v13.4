"""Domain exceptions for the analytics/BI bounded context."""

from __future__ import annotations


class AnalyticsDomainError(Exception):
    """Base for analytics/BI rule violations."""


class AnalyticsPermissionDeniedError(AnalyticsDomainError):
    pass


class MetricNotFoundError(AnalyticsDomainError):
    pass


class MetricLineageUnavailableError(AnalyticsDomainError):
    pass


class RecommendationExpiredError(AnalyticsDomainError):
    pass


class ScopeViolationError(AnalyticsDomainError):
    """Raised when a query/recommendation/alert would cross the caller's
    analytical scope (§62: OWN/TEAM/BRANCH/TERRITORY/REGION/COMPANY/ALL)."""
