from datetime import datetime, timezone

import pytest

from backend.domain.forecasting.enums import ForecastModelFamily, ForecastModelStatus
from backend.domain.forecasting.value_objects.forecast_model_definition import (
    ForecastModelDefinition,
)
from backend.shared.ids import new_uuid


def _make(**overrides) -> ForecastModelDefinition:
    fields = dict(
        id=new_uuid(),
        model_key="ses_default",
        model_family=ForecastModelFamily.SES,
        created_at=datetime(2026, 9, 4, tzinfo=timezone.utc),
    )
    fields.update(overrides)
    return ForecastModelDefinition(**fields)


def test_draft_model_constructs_without_approved_at():
    model = _make(status=ForecastModelStatus.DRAFT)
    assert model.status == ForecastModelStatus.DRAFT
    assert model.approved_at is None
    assert model.is_usable_for_forecasting() is False


def test_approved_model_requires_approved_at():
    with pytest.raises(ValueError):
        _make(status=ForecastModelStatus.APPROVED, approved_at=None)

    model = _make(
        status=ForecastModelStatus.APPROVED,
        approved_at=datetime(2026, 9, 5, tzinfo=timezone.utc),
    )
    assert model.approved_at is not None


def test_active_model_requires_approved_at():
    with pytest.raises(ValueError):
        _make(status=ForecastModelStatus.ACTIVE, approved_at=None)


def test_draft_model_must_not_have_approved_at():
    """§20-23: backtest evidence (approved_at) can't precede approval."""
    with pytest.raises(ValueError):
        _make(status=ForecastModelStatus.DRAFT,
              approved_at=datetime(2026, 9, 5, tzinfo=timezone.utc))


def test_active_model_is_usable_for_forecasting():
    model = _make(
        status=ForecastModelStatus.ACTIVE,
        approved_at=datetime(2026, 9, 5, tzinfo=timezone.utc),
    )
    assert model.is_usable_for_forecasting() is True


def test_rejects_non_uuidv7_id():
    with pytest.raises(ValueError):
        _make(id="1")


def test_rejects_version_below_one():
    with pytest.raises(ValueError):
        _make(version=0)


def test_rejects_non_positive_training_window():
    with pytest.raises(ValueError):
        _make(training_window_days=0)


def test_rejects_missing_created_at():
    with pytest.raises(ValueError):
        _make(created_at=None)
