from datetime import datetime, timezone

import pytest

from backend.domain.analytical_alerting.enums import AlertSeverity, AlertStatus, AlertType
from backend.domain.analytical_alerting.value_objects.alert import AnalyticalAlert
from backend.shared.ids import new_uuid


def _make(**overrides) -> AnalyticalAlert:
    fields = dict(
        id=new_uuid(), rule_id=new_uuid(), alert_type=AlertType.STOCKOUT_RISK,
        severity=AlertSeverity.HIGH, title="Riesgo de quiebre", message="p1 en b1 en riesgo",
        branch_id="b1", target_id="p1", evidence={"stockout_probability": "0.8"},
        fingerprint="STOCKOUT_RISK:b1:p1", status=AlertStatus.OPEN,
        created_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    fields.update(overrides)
    return AnalyticalAlert(**fields)


def test_valid_open_alert_constructs():
    alert = _make()
    assert alert.is_terminal() is False


def test_rejects_empty_evidence():
    with pytest.raises(ValueError):
        _make(evidence={})


def test_acknowledged_by_and_at_must_be_set_together():
    with pytest.raises(ValueError):
        _make(acknowledged_by="user1", acknowledged_at=None)
    with pytest.raises(ValueError):
        _make(acknowledged_by=None, acknowledged_at=datetime(2026, 9, 1, tzinfo=timezone.utc))


def test_resolved_requires_reason():
    with pytest.raises(ValueError):
        _make(status=AlertStatus.RESOLVED, resolved_by="user1",
              resolved_at=datetime(2026, 9, 2, tzinfo=timezone.utc), reason=None)


def test_valid_resolved_alert():
    alert = _make(
        status=AlertStatus.RESOLVED, resolved_by="user1",
        resolved_at=datetime(2026, 9, 2, tzinfo=timezone.utc), reason="Reabastecido",
    )
    assert alert.is_terminal() is True


def test_dismissed_status_requires_resolved_fields():
    with pytest.raises(ValueError):
        _make(status=AlertStatus.DISMISSED)


def test_expired_does_not_require_resolved_fields():
    alert = _make(status=AlertStatus.EXPIRED)
    assert alert.is_terminal() is True
    assert alert.resolved_by is None
