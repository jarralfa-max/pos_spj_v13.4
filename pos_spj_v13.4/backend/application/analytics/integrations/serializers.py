"""Domain → JSON-safe dict serializers (§57/§137, BI-22).

DTOs consumed by desktop and a future web app must be serializable
(§137: "Evitar QWidget, Qt types, sqlite Row, Decimal sin serialization
contract"). `Decimal` is serialized as a **string**, never `float` — the
same precision-preserving convention `backend/api/schemas/mobile_common.py`
already established for request bodies (`DecimalText`), applied here to
responses. Enums serialize to their `.value`; dates/datetimes to ISO 8601.
"""

from __future__ import annotations

from backend.domain.analytical_alerting.value_objects.alert import AnalyticalAlert
from backend.domain.decision_intelligence.value_objects.business_recommendation import (
    BusinessRecommendation,
)
from backend.domain.forecasting.value_objects.forecast_run import ForecastResult, ForecastRun


def serialize_forecast_run(run: ForecastRun, result: ForecastResult) -> dict:
    return {
        "runId": run.run_id,
        "modelVersionId": run.model_version_id,
        "seriesDefinitionKey": run.series_definition_key,
        "scopePolicy": run.scope_policy.value,
        "scopeValue": run.scope_value,
        "trainingFrom": run.training_from.isoformat(),
        "trainingTo": run.training_to.isoformat(),
        "forecastFrom": run.forecast_from.isoformat(),
        "forecastTo": run.forecast_to.isoformat(),
        "horizonDays": run.horizon_days,
        "generatedAt": run.generated_at.isoformat(),
        "confidenceLevel": str(run.confidence_level),
        "status": run.status.value,
        "points": [
            {
                "date": point.timestamp.isoformat(),
                "pointForecast": str(point.point_forecast),
                "lowerBound": str(point.lower_bound),
                "upperBound": str(point.upper_bound),
            }
            for point in result.points
        ],
    }


def serialize_business_recommendation(rec: BusinessRecommendation) -> dict:
    return {
        "id": rec.id,
        "recommendationType": rec.recommendation_type.value,
        "targetType": rec.target_type,
        "targetId": rec.target_id,
        "branchId": rec.branch_id,
        "title": rec.title,
        "summary": rec.summary,
        "evidence": dict(rec.evidence),
        "expectedImpact": rec.expected_impact,
        "confidence": str(rec.confidence),
        "priority": rec.priority.value,
        "status": rec.status.value,
        "validFrom": rec.valid_from.isoformat(),
        "validUntil": rec.valid_until.isoformat(),
        "createdAt": rec.created_at.isoformat(),
        "modelReference": rec.model_reference,
        "ruleReference": rec.rule_reference,
    }


def serialize_analytical_alert(alert: AnalyticalAlert) -> dict:
    return {
        "id": alert.id,
        "ruleId": alert.rule_id,
        "alertType": alert.alert_type.value,
        "severity": alert.severity.value,
        "title": alert.title,
        "message": alert.message,
        "branchId": alert.branch_id,
        "targetId": alert.target_id,
        "evidence": dict(alert.evidence),
        "fingerprint": alert.fingerprint,
        "status": alert.status.value,
        "createdAt": alert.created_at.isoformat(),
        "acknowledgedBy": alert.acknowledged_by,
        "acknowledgedAt": alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
        "resolvedBy": alert.resolved_by,
        "resolvedAt": alert.resolved_at.isoformat() if alert.resolved_at else None,
        "reason": alert.reason,
    }
