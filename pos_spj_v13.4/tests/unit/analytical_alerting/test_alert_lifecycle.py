from datetime import datetime, timezone

import pytest

from backend.domain.analytical_alerting.enums import AlertSeverity, AlertStatus, AlertType
from backend.domain.analytical_alerting.exceptions import InvalidAlertTransitionError
from backend.domain.analytical_alerting.services import alert_lifecycle as al
from backend.domain.analytical_alerting.value_objects.alert import AnalyticalAlert
from backend.shared.ids import new_uuid

_NOW = datetime(2026, 9, 1, tzinfo=timezone.utc)
_LATER = datetime(2026, 9, 2, tzinfo=timezone.utc)


def _make(status=AlertStatus.OPEN) -> AnalyticalAlert:
    fields = dict(
        id=new_uuid(), rule_id=new_uuid(), alert_type=AlertType.STOCKOUT_RISK,
        severity=AlertSeverity.HIGH, title="Riesgo de quiebre", message="p1 en b1 en riesgo",
        branch_id="b1", target_id="p1", evidence={"stockout_probability": "0.8"},
        fingerprint="STOCKOUT_RISK:b1:p1", status=status, created_at=_NOW,
    )
    if status in (AlertStatus.RESOLVED, AlertStatus.DISMISSED):
        fields.update(resolved_by="user1", resolved_at=_LATER, reason="Atendido")
    return AnalyticalAlert(**fields)


def test_full_happy_path_open_to_resolved():
    alert = _make()
    alert = al.acknowledge(alert, "user1", _NOW)
    assert alert.status == AlertStatus.ACKNOWLEDGED
    assert alert.acknowledged_by == "user1"
    alert = al.start_progress(alert)
    assert alert.status == AlertStatus.IN_PROGRESS
    alert = al.resolve(alert, "user2", _LATER, "Reabastecido")
    assert alert.status == AlertStatus.RESOLVED
    assert alert.resolved_by == "user2"
    assert alert.reason == "Reabastecido"
    assert alert.is_terminal()


def test_transition_does_not_mutate_in_place():
    original = _make()
    updated = al.acknowledge(original, "user1", _NOW)
    assert original.status == AlertStatus.OPEN
    assert updated.status == AlertStatus.ACKNOWLEDGED


def test_cannot_resolve_directly_from_open():
    alert = _make(status=AlertStatus.OPEN)
    with pytest.raises(InvalidAlertTransitionError):
        al.resolve(alert, "user1", _NOW, "reason")


def test_dismiss_reachable_from_open_without_acknowledging():
    alert = _make(status=AlertStatus.OPEN)
    dismissed = al.dismiss(alert, "user1", _NOW, "Falso positivo")
    assert dismissed.status == AlertStatus.DISMISSED
    assert dismissed.reason == "Falso positivo"


def test_resolve_requires_a_reason():
    alert = _make(status=AlertStatus.IN_PROGRESS)
    with pytest.raises(ValueError):
        al.resolve(alert, "user1", _NOW, "")


@pytest.mark.parametrize("status", [
    AlertStatus.RESOLVED, AlertStatus.DISMISSED, AlertStatus.EXPIRED,
])
def test_terminal_states_accept_no_further_transitions(status):
    alert = _make(status=status)
    with pytest.raises(InvalidAlertTransitionError):
        al.acknowledge(alert, "user1", _NOW)
    with pytest.raises(InvalidAlertTransitionError):
        al.expire(alert)


def test_expire_reachable_from_open_acknowledged_and_in_progress():
    for status in (AlertStatus.OPEN, AlertStatus.ACKNOWLEDGED, AlertStatus.IN_PROGRESS):
        expired = al.expire(_make(status=status))
        assert expired.status == AlertStatus.EXPIRED
