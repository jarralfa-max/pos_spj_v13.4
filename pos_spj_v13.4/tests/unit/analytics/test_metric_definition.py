import pytest

from backend.domain.analytics.enums import (
    AggregationType,
    CurrencyBehavior,
    FreshnessPolicy,
    ScopePolicy,
    TimeGrain,
)
from backend.domain.analytics.value_objects.metric_definition import (
    DimensionDefinition,
    MeasureDefinition,
    MetricDefinition,
)


def _make(**overrides) -> MetricDefinition:
    fields = dict(
        key="NET_SALES",
        name="Ventas netas",
        description="Suma de ventas completadas.",
        domain_owner="sales",
        formula="SUM(ventas.total)",
        unit="MXN",
        aggregation=AggregationType.SUM,
        dimensions=("branch",),
        time_grain=TimeGrain.DAILY,
        currency_behavior=CurrencyBehavior.MONETARY,
        permission="INTELIGENCIA_BI.ventas.ver",
        scope_policy=ScopePolicy.BRANCH,
        freshness_policy=FreshnessPolicy.NEAR_REAL_TIME,
    )
    fields.update(overrides)
    return MetricDefinition(**fields)


def test_valid_metric_definition_constructs():
    metric = _make()
    assert metric.key == "NET_SALES"
    assert metric.version == 1
    assert metric.versioned_key() == "NET_SALES@v1"


@pytest.mark.parametrize("field_name,value", [
    ("key", ""), ("key", "net sales"), ("key", "Net_Sales"),
    ("name", ""), ("formula", ""), ("domain_owner", ""), ("permission", ""),
])
def test_rejects_invalid_required_fields(field_name, value):
    with pytest.raises(ValueError):
        _make(**{field_name: value})


def test_rejects_version_below_one():
    with pytest.raises(ValueError):
        _make(version=0)


def test_dimension_definition_requires_key_and_name():
    DimensionDefinition(key="branch", name="Sucursal")
    with pytest.raises(ValueError):
        DimensionDefinition(key="", name="Sucursal")


def test_measure_definition_requires_key_and_name():
    MeasureDefinition(key="total_amount", name="Monto total", unit="MXN",
                       currency_behavior=CurrencyBehavior.MONETARY)
    with pytest.raises(ValueError):
        MeasureDefinition(key="", name="", unit="MXN",
                           currency_behavior=CurrencyBehavior.MONETARY)
