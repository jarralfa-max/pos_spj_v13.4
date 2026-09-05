from datetime import datetime, timedelta, timezone
from decimal import Decimal

from backend.application.analytical_alerting.services.alert_engine import AnalyticalAlertEngine
from backend.domain.analytical_alerting.enums import AlertSeverity, AlertStatus, AlertType, Comparison
from backend.domain.analytical_alerting.value_objects.alert_rule import AnalyticalAlertRule
from backend.shared.ids import new_uuid

_NOW = datetime(2026, 9, 1, tzinfo=timezone.utc)


def _rule(**overrides) -> AnalyticalAlertRule:
    fields = dict(
        id=new_uuid(), alert_type=AlertType.STOCKOUT_RISK, metric_key="stockout_probability",
        comparison=Comparison.GREATER_THAN, threshold=Decimal("0.5"),
        severity=AlertSeverity.HIGH, cooldown_minutes=60,
    )
    fields.update(overrides)
    return AnalyticalAlertRule(**fields)


def test_creates_alert_when_rule_is_breached():
    engine = AnalyticalAlertEngine()
    alert = engine.evaluate(
        rule=_rule(), metric_value=Decimal("0.8"), branch_id="b1", target_id="p1",
        evidence={"stockout_probability": "0.8"}, title="Riesgo de quiebre",
        message="p1 en b1 tiene alto riesgo de quiebre", now=_NOW,
    )
    assert alert is not None
    assert alert.status == AlertStatus.OPEN
    assert alert.severity == AlertSeverity.HIGH
    assert alert.fingerprint == "STOCKOUT_RISK:b1:p1"


def test_returns_none_when_not_breached():
    engine = AnalyticalAlertEngine()
    alert = engine.evaluate(
        rule=_rule(), metric_value=Decimal("0.2"), branch_id="b1", target_id="p1",
        evidence={"stockout_probability": "0.2"}, title="t", message="m", now=_NOW,
    )
    assert alert is None


def test_returns_none_when_rule_disabled():
    engine = AnalyticalAlertEngine()
    alert = engine.evaluate(
        rule=_rule(enabled=False), metric_value=Decimal("0.9"), branch_id="b1", target_id="p1",
        evidence={"stockout_probability": "0.9"}, title="t", message="m", now=_NOW,
    )
    assert alert is None


def test_returns_none_when_suppressed_by_cooldown():
    engine = AnalyticalAlertEngine()
    rule = _rule(cooldown_minutes=60)
    first = engine.evaluate(
        rule=rule, metric_value=Decimal("0.8"), branch_id="b1", target_id="p1",
        evidence={"stockout_probability": "0.8"}, title="t", message="m", now=_NOW,
    )
    assert first is not None

    second = engine.evaluate(
        rule=rule, metric_value=Decimal("0.85"), branch_id="b1", target_id="p1",
        evidence={"stockout_probability": "0.85"}, title="t", message="m",
        now=_NOW + timedelta(minutes=10), existing_alerts=(first,),
    )
    assert second is None


def test_fires_again_after_cooldown_elapses():
    engine = AnalyticalAlertEngine()
    rule = _rule(cooldown_minutes=60)
    first = engine.evaluate(
        rule=rule, metric_value=Decimal("0.8"), branch_id="b1", target_id="p1",
        evidence={"stockout_probability": "0.8"}, title="t", message="m", now=_NOW,
    )
    third = engine.evaluate(
        rule=rule, metric_value=Decimal("0.8"), branch_id="b1", target_id="p1",
        evidence={"stockout_probability": "0.8"}, title="t", message="m",
        now=_NOW + timedelta(minutes=90), existing_alerts=(first,),
    )
    assert third is not None
