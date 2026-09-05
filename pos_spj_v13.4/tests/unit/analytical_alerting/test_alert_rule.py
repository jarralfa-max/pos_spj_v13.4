from decimal import Decimal

import pytest

from backend.domain.analytical_alerting.enums import AlertSeverity, AlertType, Comparison
from backend.domain.analytical_alerting.value_objects.alert_rule import AnalyticalAlertRule
from backend.shared.ids import new_uuid


def _rule(**overrides) -> AnalyticalAlertRule:
    fields = dict(
        id=new_uuid(), alert_type=AlertType.STOCKOUT_RISK, metric_key="stockout_probability",
        comparison=Comparison.GREATER_THAN, threshold=Decimal("0.5"),
        severity=AlertSeverity.HIGH, cooldown_minutes=60,
    )
    fields.update(overrides)
    return AnalyticalAlertRule(**fields)


@pytest.mark.parametrize("comparison,value,expected", [
    (Comparison.GREATER_THAN, Decimal("0.6"), True),
    (Comparison.GREATER_THAN, Decimal("0.5"), False),
    (Comparison.GREATER_THAN_OR_EQUAL, Decimal("0.5"), True),
    (Comparison.LESS_THAN, Decimal("0.4"), True),
    (Comparison.LESS_THAN, Decimal("0.5"), False),
    (Comparison.LESS_THAN_OR_EQUAL, Decimal("0.5"), True),
])
def test_is_breached(comparison, value, expected):
    rule = _rule(comparison=comparison, threshold=Decimal("0.5"))
    assert rule.is_breached(value) is expected


def test_rejects_empty_metric_key():
    with pytest.raises(ValueError):
        _rule(metric_key="")


def test_rejects_negative_cooldown():
    with pytest.raises(ValueError):
        _rule(cooldown_minutes=-1)


def test_rejects_non_uuidv7_id():
    with pytest.raises(ValueError):
        _rule(id="not-a-uuid")


def test_disabled_by_default_is_false():
    rule = _rule()
    assert rule.enabled is True
    disabled_rule = _rule(enabled=False)
    assert disabled_rule.enabled is False
