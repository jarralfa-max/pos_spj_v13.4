import sqlite3
from datetime import datetime

import pytest

from backend.domain.analytical_alerting.enums import AlertSeverity, AlertStatus, AlertType
from backend.domain.analytical_alerting.value_objects.alert import AnalyticalAlert
from backend.shared.ids import new_uuid
from frontend.desktop.modules.business_intelligence.presenters.alert_explorer_presenter import (
    AlertExplorerPresenter,
    AlertTransitionError,
    map_alert_kpis,
)


def _alert(**overrides) -> AnalyticalAlert:
    defaults = dict(
        id=new_uuid(), rule_id=new_uuid(), alert_type=AlertType.MARGIN_DROP,
        severity=AlertSeverity.MEDIUM, title="t", message="m", branch_id="ALL_BRANCHES",
        target_id="margen", evidence={"metric_value": "0"}, fingerprint="MARGIN_DROP:ALL:margen",
        status=AlertStatus.OPEN, created_at=datetime(2026, 1, 1),
    )
    defaults.update(overrides)
    return AnalyticalAlert(**defaults)


def test_map_alert_kpis_reports_type_severity_and_status():
    alert = _alert()
    by_key = {c.key: c for c in map_alert_kpis(alert)}
    assert by_key["type"].value == "MARGIN_DROP"
    assert by_key["severity"].value == "MEDIUM"
    assert by_key["status"].value == "OPEN"
    assert by_key["status"].variant == "neutral"


def test_map_alert_kpis_marks_resolved_status_success():
    alert = _alert(status=AlertStatus.RESOLVED, resolved_by="u1",
                   resolved_at=datetime(2026, 1, 2), reason="fixed")
    assert {c.key: c for c in map_alert_kpis(alert)}["status"].variant == "success"


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    yield connection
    connection.close()


def test_evaluate_all_against_a_bare_connection_breaches_margin_drop(conn):
    """No schema at all: ventas=0 -> margen=0%, which IS below the default
    10% margin threshold -> a real MARGIN_DROP breach. merma=0% is NOT above
    its 3% threshold, so WASTE_SPIKE does not fire. Confirms the presenter
    runs the REAL AnalyticalAlertEngine against REAL (if degraded) dashboard
    KPIs rather than crashing or fabricating data."""
    presenter = AlertExplorerPresenter(conn)
    alerts = presenter.evaluate_all()
    assert len(alerts) == 1
    assert alerts[0].alert_type == AlertType.MARGIN_DROP
    assert alerts[0].status == AlertStatus.OPEN
    assert alerts[0].evidence["metric_key"] == "margen"


def test_apply_transition_acknowledge_requires_an_authenticated_actor(conn):
    presenter = AlertExplorerPresenter(conn)  # no actor_user_id
    with pytest.raises(AlertTransitionError):
        presenter.apply_transition(_alert(), "acknowledge")


def test_apply_transition_full_lifecycle_with_an_actor(conn):
    presenter = AlertExplorerPresenter(conn, actor_user_id=new_uuid())
    alert = _alert()
    acknowledged = presenter.apply_transition(alert, "acknowledge")
    assert acknowledged.status == AlertStatus.ACKNOWLEDGED
    in_progress = presenter.apply_transition(acknowledged, "start_progress")
    assert in_progress.status == AlertStatus.IN_PROGRESS
    resolved = presenter.apply_transition(in_progress, "resolve", reason="Corregido")
    assert resolved.status == AlertStatus.RESOLVED
    assert resolved.reason == "Corregido"


def test_apply_transition_resolve_without_a_reason_fails(conn):
    presenter = AlertExplorerPresenter(conn, actor_user_id=new_uuid())
    alert = _alert(status=AlertStatus.IN_PROGRESS)
    with pytest.raises(AlertTransitionError):
        presenter.apply_transition(alert, "resolve", reason="")


def test_apply_transition_rejects_an_invalid_jump(conn):
    presenter = AlertExplorerPresenter(conn, actor_user_id=new_uuid())
    alert = _alert()  # status=OPEN
    with pytest.raises(AlertTransitionError):
        presenter.apply_transition(alert, "resolve", reason="x")  # OPEN -> RESOLVED not allowed


def test_apply_transition_rejects_an_unknown_action(conn):
    presenter = AlertExplorerPresenter(conn, actor_user_id=new_uuid())
    with pytest.raises(AlertTransitionError):
        presenter.apply_transition(_alert(), "not_a_real_action")
