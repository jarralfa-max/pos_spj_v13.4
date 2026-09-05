import pytest

from backend.application.analytics.authorization import AnalyticsAuthorizationPolicy
from backend.application.analytics.permissions import AnalyticsPermissions
from backend.domain.analytics.exceptions import AnalyticsPermissionDeniedError


class _Checker:
    def __init__(self, allowed: set[str]) -> None:
        self._allowed = allowed

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        return permission_code in self._allowed


def test_require_denies_when_no_checker_configured():
    policy = AnalyticsAuthorizationPolicy(checker=None)
    with pytest.raises(AnalyticsPermissionDeniedError):
        policy.require("user-1", AnalyticsPermissions.FORECAST_VIEW)


def test_require_denies_unknown_permission_code():
    policy = AnalyticsAuthorizationPolicy(checker=_Checker({"INTELIGENCIA_BI.forecast.ver"}))
    with pytest.raises(AnalyticsPermissionDeniedError):
        policy.require("user-1", "INTELIGENCIA_BI.no_existe")


def test_require_denies_without_authenticated_user():
    policy = AnalyticsAuthorizationPolicy(checker=_Checker({AnalyticsPermissions.FORECAST_VIEW}))
    with pytest.raises(AnalyticsPermissionDeniedError):
        policy.require("", AnalyticsPermissions.FORECAST_VIEW)


def test_require_denies_when_checker_says_no():
    policy = AnalyticsAuthorizationPolicy(checker=_Checker(set()))
    with pytest.raises(AnalyticsPermissionDeniedError):
        policy.require("user-1", AnalyticsPermissions.FORECAST_MODEL_APPROVE)


def test_require_allows_when_checker_grants_permission():
    policy = AnalyticsAuthorizationPolicy(
        checker=_Checker({AnalyticsPermissions.FORECAST_VIEW}))
    policy.require("user-1", AnalyticsPermissions.FORECAST_VIEW)  # does not raise


def test_has_permission_probe_never_raises():
    policy = AnalyticsAuthorizationPolicy(checker=_Checker(set()))
    assert policy.has_permission("user-1", AnalyticsPermissions.FINANCE_SENSITIVE_VIEW) is False

    policy = AnalyticsAuthorizationPolicy(
        checker=_Checker({AnalyticsPermissions.FINANCE_SENSITIVE_VIEW}))
    assert policy.has_permission("user-1", AnalyticsPermissions.FINANCE_SENSITIVE_VIEW) is True
