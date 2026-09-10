from backend.application.analytics.permissions import (
    ALL_ANALYTICS_PERMISSIONS,
    AnalyticsPermissions,
)
from backend.security.permissions.codes import normalize_permission
from backend.application.security.permission_catalog import CANONICAL_MODULE_PERMISSIONS


def test_all_permission_values_are_unique_and_use_canonical_inteligencia_bi_module():
    values = [value for name, value in vars(AnalyticsPermissions).items()
              if not name.startswith("_") and isinstance(value, str)]
    assert len(values) == len(set(values)), "Permission codes must be unique"
    for value in values:
        assert value.startswith("INTELIGENCIA_BI.")


def test_all_permissions_frozenset_matches_class_constants():
    assert AnalyticsPermissions.ACCESS in ALL_ANALYTICS_PERMISSIONS
    assert AnalyticsPermissions.FORECAST_MODEL_APPROVE in ALL_ANALYTICS_PERMISSIONS
    assert AnalyticsPermissions.REMOTE_ACCESS in ALL_ANALYTICS_PERMISSIONS
    assert len(ALL_ANALYTICS_PERMISSIONS) >= 55


def test_read_and_mutation_permissions_are_distinct_codes():
    assert AnalyticsPermissions.RECOMMENDATIONS_VIEW != AnalyticsPermissions.RECOMMENDATIONS_APPROVE
    assert AnalyticsPermissions.ALERTS_VIEW != AnalyticsPermissions.ALERTS_ACKNOWLEDGE
    assert AnalyticsPermissions.FORECAST_MODEL_APPROVE != AnalyticsPermissions.FORECAST_MODEL_ACTIVATE


def test_sensitive_finance_metrics_have_their_own_dedicated_code():
    """§117: a branch manager can see the branch dashboard without seeing
    company cash/CxC/CxP/payroll/capital — those need a distinct code from
    the general finance-view code."""
    assert AnalyticsPermissions.FINANCE_SENSITIVE_VIEW != AnalyticsPermissions.FINANCE_VIEW


def test_every_permission_action_suffix_is_registered_in_the_canonical_catalog():
    catalog_actions = set(CANONICAL_MODULE_PERMISSIONS["INTELIGENCIA_BI"])
    for value in ALL_ANALYTICS_PERMISSIONS:
        module, _, action = value.partition(".")
        assert module == "INTELIGENCIA_BI"
        assert action in catalog_actions, f"{value} missing from CANONICAL_MODULE_PERMISSIONS"


def test_normalize_permission_matches_catalog_case_insensitive_contract():
    assert (normalize_permission(AnalyticsPermissions.FORECAST_MODEL_APPROVE)
            == "INTELIGENCIA_BI.FORECAST.MODELO.APROBAR")
