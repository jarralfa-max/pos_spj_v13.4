from datetime import date, datetime, timezone
from decimal import Decimal

from backend.api.mobile_session import MobileIdentity
from backend.application.analytics.integrations.analytics_api_workflow import (
    AnalyticsApiWorkflow,
)
from backend.domain.analytical_alerting.enums import AlertSeverity, AlertStatus, AlertType
from backend.domain.analytical_alerting.value_objects.alert import AnalyticalAlert
from backend.domain.analytics.enums import ScopePolicy
from backend.domain.decision_intelligence.enums import (
    BusinessRecommendationType,
    RecommendationStatus,
)
from backend.domain.decision_intelligence.value_objects.business_recommendation import (
    BusinessRecommendation,
)
from backend.domain.forecasting.enums import ForecastRunStatus, RecommendationPriority
from backend.domain.forecasting.value_objects.forecast_run import (
    ForecastResult,
    ForecastResultPoint,
    ForecastRun,
)
from backend.shared.ids import new_uuid

_IDENTITY = MobileIdentity(
    user_id="u1", display_name="Ana", branch_id="b1", branch_name="Centro",
    warehouse_id="b1", warehouse_name="Centro", device_id="dev1",
    permissions=("INTELIGENCIA_BI.forecast.ver",),
)


class _FakeForecastRunRepository:
    def __init__(self, run, result):
        self._run = run
        self._result = result

    def save_run(self, run, result):
        raise NotImplementedError

    def get_run(self, run_id):
        return self._run

    def get_result(self, run_id):
        return self._result

    def list_runs(self, series_key, limit=20):
        return (self._run,)


class _FakeRecommendationProvider:
    def __init__(self, recs):
        self._recs = recs

    def list_recommendations(self, branch_id):
        return tuple(r for r in self._recs if r.branch_id == branch_id)


class _FakeAlertProvider:
    def __init__(self, alerts):
        self._alerts = alerts

    def list_alerts(self, branch_id):
        return tuple(a for a in self._alerts if a.branch_id == branch_id)


def _run_and_result():
    run = ForecastRun(
        run_id=new_uuid(), model_version_id=new_uuid(), series_definition_key="daily_sales_by_product",
        scope_policy=ScopePolicy.BRANCH, scope_value="b1",
        training_from=date(2026, 8, 1), training_to=date(2026, 8, 10),
        forecast_from=date(2026, 8, 11), forecast_to=date(2026, 8, 12),
        horizon_days=2, generated_at=datetime(2026, 8, 11, tzinfo=timezone.utc),
        confidence_level=Decimal("0.90"), status=ForecastRunStatus.COMPLETED,
    )
    result = ForecastResult(run_id=run.run_id, points=(
        ForecastResultPoint(timestamp=date(2026, 8, 11), point_forecast=Decimal("10"),
                            lower_bound=Decimal("8"), upper_bound=Decimal("12")),
    ))
    return run, result


def test_list_forecasts_returns_run_summaries():
    run, result = _run_and_result()
    workflow = AnalyticsApiWorkflow(
        _FakeForecastRunRepository(run, result), _FakeRecommendationProvider([]),
        _FakeAlertProvider([]),
    )
    payload = workflow.list_forecasts(_IDENTITY, "daily_sales_by_product")
    assert payload["runs"][0]["runId"] == run.run_id


def test_get_forecast_returns_full_serialized_run():
    run, result = _run_and_result()
    workflow = AnalyticsApiWorkflow(
        _FakeForecastRunRepository(run, result), _FakeRecommendationProvider([]),
        _FakeAlertProvider([]),
    )
    payload = workflow.get_forecast(_IDENTITY, run.run_id)
    assert payload["points"][0]["pointForecast"] == "10"


def test_list_recommendations_scopes_by_identity_branch():
    rec_b1 = BusinessRecommendation(
        id=new_uuid(), recommendation_type=BusinessRecommendationType.PURCHASE_MORE,
        target_type="product", target_id="p1", branch_id="b1", title="t", summary="s",
        evidence={"x": "1"}, expected_impact="impact", confidence=Decimal("0.8"),
        priority=RecommendationPriority.HIGH, status=RecommendationStatus.NEW,
        valid_from=date(2026, 9, 1), valid_until=date(2026, 9, 8),
        created_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    rec_b2 = BusinessRecommendation(
        id=new_uuid(), recommendation_type=BusinessRecommendationType.PURCHASE_MORE,
        target_type="product", target_id="p2", branch_id="b2", title="t", summary="s",
        evidence={"x": "1"}, expected_impact="impact", confidence=Decimal("0.8"),
        priority=RecommendationPriority.HIGH, status=RecommendationStatus.NEW,
        valid_from=date(2026, 9, 1), valid_until=date(2026, 9, 8),
        created_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    run, result = _run_and_result()
    workflow = AnalyticsApiWorkflow(
        _FakeForecastRunRepository(run, result),
        _FakeRecommendationProvider([rec_b1, rec_b2]), _FakeAlertProvider([]),
    )
    payload = workflow.list_recommendations(_IDENTITY)  # identity.branch_id == "b1"
    assert len(payload["recommendations"]) == 1
    assert payload["recommendations"][0]["targetId"] == "p1"


def test_list_alerts_scopes_by_identity_branch():
    alert = AnalyticalAlert(
        id=new_uuid(), rule_id=new_uuid(), alert_type=AlertType.STOCKOUT_RISK,
        severity=AlertSeverity.HIGH, title="t", message="m", branch_id="b1", target_id="p1",
        evidence={"x": "1"}, fingerprint="STOCKOUT_RISK:b1:p1", status=AlertStatus.OPEN,
        created_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    run, result = _run_and_result()
    workflow = AnalyticsApiWorkflow(
        _FakeForecastRunRepository(run, result), _FakeRecommendationProvider([]),
        _FakeAlertProvider([alert]),
    )
    payload = workflow.list_alerts(_IDENTITY)
    assert payload["alerts"][0]["id"] == alert.id
