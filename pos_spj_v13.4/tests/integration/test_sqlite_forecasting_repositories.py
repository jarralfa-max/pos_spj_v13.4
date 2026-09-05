"""BI-11 — SqliteForecastModelRepository / SqliteForecastRunRepository
against the real `forecast_models`/`forecast_runs`/`forecast_result_points`
schema (migration 254), created directly via `create_forecasting_schema`
rather than the full migration engine (see BI-4/BI-8 notes on the
pre-existing `fresh_db()` bootstrap bug)."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from backend.domain.analytics.enums import ScopePolicy
from backend.domain.forecasting.enums import ForecastModelFamily, ForecastModelStatus, ForecastRunStatus
from backend.domain.forecasting.exceptions import ForecastModelNotFoundError, ForecastRunNotFoundError
from backend.domain.forecasting.value_objects.forecast_model_definition import ForecastModelDefinition
from backend.domain.forecasting.value_objects.forecast_run import (
    ForecastResult,
    ForecastResultPoint,
    ForecastRun,
)
from backend.infrastructure.db.repositories.forecasting.sqlite_forecast_model_repository import (
    SqliteForecastModelRepository,
)
from backend.infrastructure.db.repositories.forecasting.sqlite_forecast_run_repository import (
    SqliteForecastRunRepository,
)
from backend.infrastructure.db.schema.forecasting_schema import create_forecasting_schema
from backend.shared.ids import new_uuid


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    create_forecasting_schema(c)
    yield c
    c.close()


def _model(**overrides) -> ForecastModelDefinition:
    fields = dict(
        id=new_uuid(), model_key="ses_default", model_family=ForecastModelFamily.SES,
        created_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    fields.update(overrides)
    return ForecastModelDefinition(**fields)


class TestSqliteForecastModelRepository:
    def test_save_and_get_round_trip(self, conn):
        repo = SqliteForecastModelRepository(conn)
        model = _model(parameters={"alpha": "0.3"}, feature_schema=("day_of_week",))
        repo.save(model)
        fetched = repo.get("ses_default", 1)
        assert fetched.id == model.id
        assert fetched.parameters == {"alpha": "0.3"}
        assert fetched.feature_schema == ("day_of_week",)
        assert fetched.status == ForecastModelStatus.DRAFT

    def test_get_missing_model_raises(self, conn):
        repo = SqliteForecastModelRepository(conn)
        with pytest.raises(ForecastModelNotFoundError):
            repo.get("does_not_exist", 1)

    def test_get_active_returns_none_when_no_active_version(self, conn):
        repo = SqliteForecastModelRepository(conn)
        repo.save(_model(status=ForecastModelStatus.DRAFT))
        assert repo.get_active("ses_default") is None

    def test_get_active_returns_the_active_version(self, conn):
        repo = SqliteForecastModelRepository(conn)
        repo.save(_model(
            status=ForecastModelStatus.ACTIVE,
            approved_at=datetime(2026, 9, 2, tzinfo=timezone.utc)))
        active = repo.get_active("ses_default")
        assert active is not None
        assert active.status == ForecastModelStatus.ACTIVE

    def test_status_transition_upserts_same_id_same_version(self, conn):
        """Approving a model is a status transition on the SAME row (id,
        model_key, version unchanged) — not a new version."""
        repo = SqliteForecastModelRepository(conn)
        draft = _model(status=ForecastModelStatus.DRAFT)
        repo.save(draft)

        approved = ForecastModelDefinition(
            id=draft.id, model_key=draft.model_key, model_family=draft.model_family,
            parameters=draft.parameters, training_window_days=draft.training_window_days,
            minimum_history_days=draft.minimum_history_days, feature_schema=draft.feature_schema,
            status=ForecastModelStatus.APPROVED, version=draft.version,
            created_at=draft.created_at, approved_at=datetime(2026, 9, 3, tzinfo=timezone.utc),
        )
        repo.save(approved)

        versions = repo.list_versions("ses_default")
        assert len(versions) == 1
        assert versions[0].status == ForecastModelStatus.APPROVED
        assert versions[0].id == draft.id

    def test_new_training_iteration_is_a_new_version_row(self, conn):
        repo = SqliteForecastModelRepository(conn)
        repo.save(_model(version=1))
        repo.save(_model(version=2))
        versions = repo.list_versions("ses_default")
        assert [v.version for v in versions] == [1, 2]


class TestSqliteForecastRunRepository:
    def _run_and_result(self, run_id: str, model_version_id: str):
        run = ForecastRun(
            run_id=run_id, model_version_id=model_version_id,
            series_definition_key="daily_sales_by_product",
            scope_policy=ScopePolicy.BRANCH, scope_value="branch-1",
            training_from=date(2026, 8, 1), training_to=date(2026, 8, 10),
            forecast_from=date(2026, 8, 11), forecast_to=date(2026, 8, 12),
            horizon_days=2, generated_at=datetime(2026, 8, 11, tzinfo=timezone.utc),
            confidence_level=Decimal("0.90"), status=ForecastRunStatus.COMPLETED,
        )
        result = ForecastResult(run_id=run_id, points=(
            ForecastResultPoint(timestamp=date(2026, 8, 11), point_forecast=Decimal("10"),
                                 lower_bound=Decimal("8"), upper_bound=Decimal("12")),
            ForecastResultPoint(timestamp=date(2026, 8, 12), point_forecast=Decimal("11"),
                                 lower_bound=Decimal("9"), upper_bound=Decimal("13")),
        ))
        return run, result

    def test_save_and_get_run_round_trip(self, conn):
        model_repo = SqliteForecastModelRepository(conn)
        model = _model()
        model_repo.save(model)

        run_repo = SqliteForecastRunRepository(conn)
        run_id = new_uuid()
        run, result = self._run_and_result(run_id, model.id)
        run_repo.save_run(run, result)

        fetched_run = run_repo.get_run(run_id)
        assert fetched_run.scope_value == "branch-1"
        assert fetched_run.horizon_days == 2

        fetched_result = run_repo.get_result(run_id)
        assert len(fetched_result.points) == 2
        assert fetched_result.points[0].point_forecast == Decimal("10")
        assert fetched_result.points[1].lower_bound == Decimal("9")

    def test_get_missing_run_raises(self, conn):
        run_repo = SqliteForecastRunRepository(conn)
        with pytest.raises(ForecastRunNotFoundError):
            run_repo.get_run(new_uuid())

    def test_save_run_rejects_mismatched_result_run_id(self, conn):
        model_repo = SqliteForecastModelRepository(conn)
        model = _model()
        model_repo.save(model)
        run_repo = SqliteForecastRunRepository(conn)
        run, result = self._run_and_result(new_uuid(), model.id)
        _, other_result = self._run_and_result(new_uuid(), model.id)
        with pytest.raises(ValueError):
            run_repo.save_run(run, other_result)

    def test_list_runs_orders_by_generated_at_descending(self, conn):
        model_repo = SqliteForecastModelRepository(conn)
        model = _model()
        model_repo.save(model)
        run_repo = SqliteForecastRunRepository(conn)

        run1, result1 = self._run_and_result(new_uuid(), model.id)
        run_repo.save_run(run1, result1)

        run2 = ForecastRun(
            run_id=new_uuid(), model_version_id=model.id,
            series_definition_key="daily_sales_by_product",
            scope_policy=ScopePolicy.BRANCH, scope_value="branch-1",
            training_from=date(2026, 8, 1), training_to=date(2026, 8, 10),
            forecast_from=date(2026, 8, 11), forecast_to=date(2026, 8, 12),
            horizon_days=2, generated_at=datetime(2026, 8, 12, tzinfo=timezone.utc),
            confidence_level=Decimal("0.90"), status=ForecastRunStatus.COMPLETED,
        )
        result2 = ForecastResult(run_id=run2.run_id, points=result1.points)
        run_repo.save_run(run2, result2)

        runs = run_repo.list_runs("daily_sales_by_product")
        assert runs[0].run_id == run2.run_id
        assert runs[1].run_id == run1.run_id
