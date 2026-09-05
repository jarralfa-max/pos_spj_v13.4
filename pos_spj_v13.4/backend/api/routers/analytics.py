"""BI Analytics API (§57-59, BI-22) — read-only by default (§59: "La web de
monitoreo remoto debe comenzar como read-only analytics"). No mutation
endpoint exists here; approving/rejecting a `BusinessRecommendation` or
acknowledging an `AnalyticalAlert` stays a desktop/future-Use-Case action,
not something this router exposes yet.

Reuses the SAME signed mobile session (`mobile_identity`,
`backend/api/mobile_session.py`) every other router already uses — a BI web
reader is not a special case requiring its own auth mechanism (§58: no
shared admin token, no static API key).

Controllers here do no domain logic themselves — every read delegates to
`AnalyticsApiWorkflow` (`backend/application/analytics/integrations/
analytics_api_workflow.py`), same "thin router, real workflow" shape as
`routers/driver_logistics.py`.
"""

from __future__ import annotations

from typing import Protocol

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from backend.api.mobile_session import MobileIdentity, mobile_identity
from backend.application.analytics.permissions import AnalyticsPermissions

router = APIRouter(tags=["analytics"])


class AnalyticsApiWorkflowProtocol(Protocol):
    def list_forecasts(self, identity: MobileIdentity, series_key: str, limit: int = 20) -> dict: ...
    def get_forecast(self, identity: MobileIdentity, run_id: str) -> dict: ...
    def list_recommendations(self, identity: MobileIdentity) -> dict: ...
    def list_alerts(self, identity: MobileIdentity) -> dict: ...


def workflow(request: Request) -> AnalyticsApiWorkflowProtocol:
    value = getattr(request.app.state, "analytics_workflow", None)
    if value is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Servicio de analítica no configurado")
    return value


def _require_permission(user: MobileIdentity, permission_code: str) -> None:
    normalized = permission_code.upper()
    if not any(p.upper() == normalized for p in user.permissions):
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Falta permiso {permission_code}")


@router.get("/bi/forecasts/{series_key}")
def list_forecasts(
    series_key: str,
    limit: int = Query(default=20, ge=1, le=100),
    user: MobileIdentity = Depends(mobile_identity),
    service: AnalyticsApiWorkflowProtocol = Depends(workflow),
) -> dict:
    _require_permission(user, AnalyticsPermissions.FORECAST_VIEW)
    return service.list_forecasts(user, series_key, limit)


@router.get("/bi/forecasts/{series_key}/{run_id}")
def get_forecast(
    series_key: str,
    run_id: str,
    user: MobileIdentity = Depends(mobile_identity),
    service: AnalyticsApiWorkflowProtocol = Depends(workflow),
) -> dict:
    _require_permission(user, AnalyticsPermissions.FORECAST_VIEW)
    return service.get_forecast(user, run_id)


@router.get("/bi/recommendations")
def list_recommendations(
    user: MobileIdentity = Depends(mobile_identity),
    service: AnalyticsApiWorkflowProtocol = Depends(workflow),
) -> dict:
    _require_permission(user, AnalyticsPermissions.RECOMMENDATIONS_VIEW)
    return service.list_recommendations(user)


@router.get("/bi/alerts")
def list_alerts(
    user: MobileIdentity = Depends(mobile_identity),
    service: AnalyticsApiWorkflowProtocol = Depends(workflow),
) -> dict:
    _require_permission(user, AnalyticsPermissions.ALERTS_VIEW)
    return service.list_alerts(user)
