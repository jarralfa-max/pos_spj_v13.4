from datetime import datetime, timezone

import pytest

from backend.application.analytics.services.metric_registry import MetricRegistry
from backend.domain.analytics.enums import (
    AggregationType,
    CurrencyBehavior,
    FreshnessPolicy,
    ScopePolicy,
    TimeGrain,
)
from backend.domain.analytics.exceptions import MetricNotFoundError
from backend.domain.analytics.value_objects.metric_definition import MetricDefinition


def _metric(key="NET_SALES", version=1, domain_owner="sales") -> MetricDefinition:
    return MetricDefinition(
        key=key, name="Ventas netas", description="…", domain_owner=domain_owner,
        formula="SUM(ventas.total)", unit="MXN", aggregation=AggregationType.SUM,
        dimensions=("branch",), time_grain=TimeGrain.DAILY,
        currency_behavior=CurrencyBehavior.MONETARY,
        permission="INTELIGENCIA_BI.ventas.ver", scope_policy=ScopePolicy.BRANCH,
        freshness_policy=FreshnessPolicy.NEAR_REAL_TIME, version=version,
    )


def test_register_and_get_round_trip():
    registry = MetricRegistry()
    registry.register(_metric())
    assert registry.get("NET_SALES").key == "NET_SALES"


def test_get_unknown_metric_raises_metric_not_found_error():
    registry = MetricRegistry()
    with pytest.raises(MetricNotFoundError):
        registry.get("DOES_NOT_EXIST")


def test_registering_same_or_lower_version_is_rejected():
    """§69: forecast/metric history is never silently overwritten."""
    registry = MetricRegistry()
    registry.register(_metric(version=1))
    with pytest.raises(ValueError):
        registry.register(_metric(version=1))
    with pytest.raises(ValueError):
        registry.register(_metric(version=0))


def test_registering_a_higher_version_replaces_the_definition():
    registry = MetricRegistry()
    registry.register(_metric(version=1))
    registry.register(_metric(version=2))
    assert registry.get("NET_SALES").version == 2


def test_by_domain_owner_filters_correctly():
    registry = MetricRegistry()
    registry.register(_metric(key="NET_SALES", domain_owner="sales"))
    registry.register(_metric(key="INVENTORY_VALUE", domain_owner="inventory"))
    sales_metrics = registry.by_domain_owner("sales")
    assert {m.key for m in sales_metrics} == {"NET_SALES"}


def test_lineage_for_builds_lineage_from_definition():
    registry = MetricRegistry()
    registry.register(_metric())
    computed_at = datetime(2026, 9, 4, tzinfo=timezone.utc)
    lineage = registry.lineage_for(
        "NET_SALES", period_description="Septiembre 2026",
        filters_applied=("branch=1",), computed_at=computed_at,
    )
    assert lineage.metric_key == "NET_SALES"
    assert lineage.metric_version == 1
    assert lineage.formula == "SUM(ventas.total)"
    assert lineage.period_description == "Septiembre 2026"
    assert lineage.filters_applied == ("branch=1",)
    assert lineage.computed_at == computed_at


def test_lineage_for_unknown_metric_raises():
    registry = MetricRegistry()
    with pytest.raises(MetricNotFoundError):
        registry.lineage_for("DOES_NOT_EXIST", period_description="hoy")
