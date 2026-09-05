from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from backend.domain.analytics.enums import ScopePolicy
from backend.domain.analytics.value_objects.analytical_snapshot import (
    AnalyticalSnapshot,
    SnapshotKind,
)


def _make(**overrides) -> AnalyticalSnapshot:
    fields = dict(
        kind=SnapshotKind.DAILY_SALES,
        scope_policy=ScopePolicy.BRANCH,
        scope_value="branch-1",
        period=date(2026, 9, 4),
        values={"NET_SALES": Decimal("1000.00")},
        computed_at=datetime(2026, 9, 4, tzinfo=timezone.utc),
        source_event_ids=("evt-1", "evt-2"),
    )
    fields.update(overrides)
    return AnalyticalSnapshot(**fields)


def test_valid_snapshot_constructs_and_reads_value():
    snapshot = _make()
    assert snapshot.value("NET_SALES") == Decimal("1000.00")


def test_rejects_empty_scope_value():
    with pytest.raises(ValueError):
        _make(scope_value="")


def test_rejects_empty_values():
    with pytest.raises(ValueError):
        _make(values={})


def test_rejects_non_decimal_values():
    with pytest.raises(TypeError):
        _make(values={"NET_SALES": 1000.0})


def test_rejects_missing_source_event_ids():
    """§64: a snapshot must be reconstructible — traceable to the events
    that produced it."""
    with pytest.raises(ValueError):
        _make(source_event_ids=())
