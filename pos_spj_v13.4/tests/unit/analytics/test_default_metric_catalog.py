from backend.application.analytics.permissions import ALL_ANALYTICS_PERMISSIONS
from backend.application.analytics.services.default_metric_catalog import build_default_catalog


def test_default_catalog_registers_every_metric_without_error():
    registry = build_default_catalog()
    assert len(registry.all()) >= 13


def test_default_catalog_has_unique_keys():
    registry = build_default_catalog()
    keys = [m.key for m in registry.all()]
    assert len(keys) == len(set(keys))


def test_default_catalog_expected_metrics_present():
    registry = build_default_catalog()
    for key in ("NET_SALES", "COGS", "NET_PROFIT", "GROSS_MARGIN_PCT",
                "AVERAGE_TICKET", "INVENTORY_VALUE", "INVENTORY_TURNOVER",
                "WASTE_RATE", "FORECAST_ERROR", "CUSTOMER_FREQUENCY"):
        assert registry.get(key) is not None


def test_every_default_metric_permission_is_a_real_registered_permission():
    registry = build_default_catalog()
    for metric in registry.all():
        assert metric.permission in ALL_ANALYTICS_PERMISSIONS, (
            f"{metric.key} references unregistered permission {metric.permission}")


def test_sensitive_finance_metrics_require_the_sensitive_permission():
    registry = build_default_catalog()
    for key in ("ACCOUNTS_RECEIVABLE", "ACCOUNTS_PAYABLE"):
        assert registry.get(key).permission == "INTELIGENCIA_BI.finanzas.sensible.ver"
