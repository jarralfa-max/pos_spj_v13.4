"""AnalyticsApiWorkflow — the REAL implementation `backend/api/routers/
analytics.py` calls into (§57-59, BI-22). Mirrors
`OrdersDeliveryDriverWorkflow`'s shape (methods take the caller's
`MobileIdentity` first, return JSON-ready dicts via `serializers.py`).

Forecast reads are backed by the real `ForecastRunRepositoryPort` (BI-11 —
genuine SQLite persistence exists). Recommendations/alerts are backed by
simple provider ports instead, since `BusinessRecommendation`/
`AnalyticalAlert` (BI-18/BI-20) have no persistence yet — documented there,
not hidden here; a real infra implementation of these two providers arrives
alongside that persistence.
"""

from __future__ import annotations

from typing import Protocol

from backend.api.mobile_session import MobileIdentity
from backend.application.analytics.integrations.serializers import (
    serialize_analytical_alert,
    serialize_business_recommendation,
    serialize_forecast_run,
)
from backend.domain.decision_intelligence.value_objects.business_recommendation import (
    BusinessRecommendation,
)
from backend.domain.analytical_alerting.value_objects.alert import AnalyticalAlert
from backend.domain.forecasting.repository_ports import ForecastRunRepositoryPort


class RecommendationProvider(Protocol):
    def list_recommendations(self, branch_id: str | None) -> tuple[BusinessRecommendation, ...]: ...


class AlertProvider(Protocol):
    def list_alerts(self, branch_id: str | None) -> tuple[AnalyticalAlert, ...]: ...


class AnalyticsApiWorkflow:
    def __init__(
        self,
        forecast_run_repository: ForecastRunRepositoryPort,
        recommendation_provider: RecommendationProvider,
        alert_provider: AlertProvider,
    ) -> None:
        self._forecast_run_repository = forecast_run_repository
        self._recommendation_provider = recommendation_provider
        self._alert_provider = alert_provider

    def list_forecasts(self, identity: MobileIdentity, series_key: str, limit: int = 20) -> dict:
        runs = self._forecast_run_repository.list_runs(series_key, limit)
        return {"runs": [{"runId": r.run_id, "generatedAt": r.generated_at.isoformat(),
                          "status": r.status.value} for r in runs]}

    def get_forecast(self, identity: MobileIdentity, run_id: str) -> dict:
        run = self._forecast_run_repository.get_run(run_id)
        result = self._forecast_run_repository.get_result(run_id)
        return serialize_forecast_run(run, result)

    def list_recommendations(self, identity: MobileIdentity) -> dict:
        recs = self._recommendation_provider.list_recommendations(identity.branch_id)
        return {"recommendations": [serialize_business_recommendation(r) for r in recs]}

    def list_alerts(self, identity: MobileIdentity) -> dict:
        alerts = self._alert_provider.list_alerts(identity.branch_id)
        return {"alerts": [serialize_analytical_alert(a) for a in alerts]}
