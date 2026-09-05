"""BI-22 — the analytics API router end-to-end against a real
`forecast_*` SQLite schema (migration 254) and the real
`SqliteForecastRunRepository` (BI-11), through a real FastAPI `TestClient`
— same pattern as `tests/integration/logistics/test_driver_pwa_api.py`
(only the login credential check is faked, matching every other mobile
router's test convention).
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from backend.api.main import create_app
from backend.api.mobile_session import MobileIdentity, MobileSessionTokenService
from backend.application.analytics.integrations.analytics_api_workflow import (
    AnalyticsApiWorkflow,
)
from backend.domain.analytics.enums import ScopePolicy
from backend.domain.forecasting.enums import ForecastRunStatus
from backend.domain.forecasting.value_objects.forecast_run import (
    ForecastResult,
    ForecastResultPoint,
    ForecastRun,
)
from backend.infrastructure.db.repositories.forecasting.sqlite_forecast_run_repository import (
    SqliteForecastRunRepository,
)
from backend.infrastructure.db.schema.forecasting_schema import create_forecasting_schema
from backend.shared.ids import new_uuid

_ALL_BI_PERMISSIONS = (
    "INTELIGENCIA_BI.forecast.ver", "INTELIGENCIA_BI.recomendacion.ver",
    "INTELIGENCIA_BI.alerta.ver",
)


class _Verifier:
    def __init__(self, user_id: str, branch_id: str) -> None:
        self._user_id = user_id
        self._branch_id = branch_id

    def authenticate_mobile(self, username, password, device_id):
        if password != "secret":
            return None
        return MobileIdentity(
            self._user_id, "Ana", self._branch_id, "Centro", self._branch_id, "Centro",
            device_id, _ALL_BI_PERMISSIONS)


class _EmptyRecommendationProvider:
    def list_recommendations(self, branch_id):
        return ()


class _EmptyAlertProvider:
    def list_alerts(self, branch_id):
        return ()


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    create_forecasting_schema(connection)
    yield connection
    connection.close()


def _seed_run(conn, branch_id: str) -> str:
    run = ForecastRun(
        run_id=new_uuid(), model_version_id=new_uuid(),
        series_definition_key="daily_sales_by_product",
        scope_policy=ScopePolicy.BRANCH, scope_value=branch_id,
        training_from=date(2026, 8, 1), training_to=date(2026, 8, 10),
        forecast_from=date(2026, 8, 11), forecast_to=date(2026, 8, 12),
        horizon_days=2, generated_at=datetime(2026, 8, 11, tzinfo=timezone.utc),
        confidence_level=Decimal("0.90"), status=ForecastRunStatus.COMPLETED,
    )
    result = ForecastResult(run_id=run.run_id, points=(
        ForecastResultPoint(timestamp=date(2026, 8, 11), point_forecast=Decimal("10"),
                            lower_bound=Decimal("8"), upper_bound=Decimal("12")),
    ))
    SqliteForecastRunRepository(conn).save_run(run, result)
    return run.run_id


def _client(conn):
    app = create_app()
    user_id, branch_id = new_uuid(), new_uuid()
    app.state.mobile_session_service = MobileSessionTokenService(
        b"a" * 32, _Verifier(user_id, branch_id))
    app.state.analytics_workflow = AnalyticsApiWorkflow(
        SqliteForecastRunRepository(conn), _EmptyRecommendationProvider(), _EmptyAlertProvider())
    return TestClient(app), user_id, branch_id


def _login(api) -> dict:
    response = api.post("/api/mobile/session",
                        json={"username": "u1", "password": "secret", "deviceId": "phone-1"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['accessToken']}"}


def test_requires_authentication(conn):
    api, _, _ = _client(conn)
    assert api.get("/api/bi/forecasts/daily_sales_by_product").status_code == 401


def test_returns_503_when_workflow_not_configured(conn):
    app = create_app()
    user_id, branch_id = new_uuid(), new_uuid()
    app.state.mobile_session_service = MobileSessionTokenService(
        b"a" * 32, _Verifier(user_id, branch_id))
    api = TestClient(app)
    headers = _login(api)
    response = api.get("/api/bi/forecasts/daily_sales_by_product", headers=headers)
    assert response.status_code == 503


def test_list_forecasts_returns_seeded_run(conn):
    api, user_id, branch_id = _client(conn)
    run_id = _seed_run(conn, branch_id)
    headers = _login(api)

    response = api.get("/api/bi/forecasts/daily_sales_by_product", headers=headers)
    assert response.status_code == 200
    assert response.json()["runs"][0]["runId"] == run_id


def test_get_forecast_returns_full_result(conn):
    api, user_id, branch_id = _client(conn)
    run_id = _seed_run(conn, branch_id)
    headers = _login(api)

    response = api.get(f"/api/bi/forecasts/daily_sales_by_product/{run_id}", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["points"][0]["pointForecast"] == "10"
    assert body["confidenceLevel"] == "0.90"


def test_list_recommendations_and_alerts_return_empty_lists(conn):
    api, user_id, branch_id = _client(conn)
    headers = _login(api)

    recs = api.get("/api/bi/recommendations", headers=headers)
    assert recs.status_code == 200
    assert recs.json() == {"recommendations": []}

    alerts = api.get("/api/bi/alerts", headers=headers)
    assert alerts.status_code == 200
    assert alerts.json() == {"alerts": []}


def test_missing_permission_returns_403(conn):
    app = create_app()
    user_id, branch_id = new_uuid(), new_uuid()

    class _NoPermVerifier:
        def authenticate_mobile(self, username, password, device_id):
            return MobileIdentity(user_id, "Ana", branch_id, "Centro", branch_id, "Centro",
                                  device_id, ())  # no permissions granted

    app.state.mobile_session_service = MobileSessionTokenService(b"a" * 32, _NoPermVerifier())
    app.state.analytics_workflow = AnalyticsApiWorkflow(
        SqliteForecastRunRepository(conn), _EmptyRecommendationProvider(), _EmptyAlertProvider())
    api = TestClient(app)
    headers = _login(api)

    response = api.get("/api/bi/forecasts/daily_sales_by_product", headers=headers)
    assert response.status_code == 403
