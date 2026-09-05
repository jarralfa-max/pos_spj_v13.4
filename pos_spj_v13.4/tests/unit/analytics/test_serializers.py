from datetime import date, datetime, timezone
from decimal import Decimal

from backend.application.analytics.integrations.serializers import (
    serialize_analytical_alert,
    serialize_business_recommendation,
    serialize_forecast_run,
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


def test_serialize_forecast_run_produces_json_safe_types():
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
    payload = serialize_forecast_run(run, result)

    assert payload["runId"] == run.run_id
    assert payload["confidenceLevel"] == "0.90"
    assert payload["status"] == "COMPLETED"
    assert payload["trainingFrom"] == "2026-08-01"
    assert payload["points"][0]["pointForecast"] == "10"
    assert all(isinstance(v, (str, int, list, dict)) for v in payload.values())


def test_serialize_business_recommendation_produces_json_safe_types():
    rec = BusinessRecommendation(
        id=new_uuid(), recommendation_type=BusinessRecommendationType.PURCHASE_MORE,
        target_type="product", target_id="p1", branch_id="b1", title="t", summary="s",
        evidence={"suggested_quantity": "20"}, expected_impact="impact",
        confidence=Decimal("0.8"), priority=RecommendationPriority.HIGH,
        status=RecommendationStatus.NEW, valid_from=date(2026, 9, 1),
        valid_until=date(2026, 9, 8), created_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        model_reference="forecasting.purchase_planning_service",
    )
    payload = serialize_business_recommendation(rec)

    assert payload["recommendationType"] == "PURCHASE_MORE"
    assert payload["confidence"] == "0.8"
    assert payload["priority"] == "HIGH"
    assert payload["status"] == "NEW"
    assert payload["modelReference"] == "forecasting.purchase_planning_service"
    assert payload["ruleReference"] is None


def test_serialize_analytical_alert_produces_json_safe_types():
    alert = AnalyticalAlert(
        id=new_uuid(), rule_id=new_uuid(), alert_type=AlertType.STOCKOUT_RISK,
        severity=AlertSeverity.HIGH, title="t", message="m", branch_id="b1", target_id="p1",
        evidence={"stockout_probability": "0.8"}, fingerprint="STOCKOUT_RISK:b1:p1",
        status=AlertStatus.OPEN, created_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    payload = serialize_analytical_alert(alert)

    assert payload["alertType"] == "STOCKOUT_RISK"
    assert payload["severity"] == "HIGH"
    assert payload["status"] == "OPEN"
    assert payload["acknowledgedBy"] is None
    assert payload["createdAt"] == "2026-09-01T00:00:00+00:00"
