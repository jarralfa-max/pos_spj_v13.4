"""SET-18 — "Metrics": ContentImpression + impression_metrics_policy.
summarize_impressions. Pure domain — no DB.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.domain.customer_display.entities.content_impression import ContentImpression
from backend.domain.customer_display.exceptions import CustomerDisplayInvalidValueError
from backend.domain.customer_display.policies.impression_metrics_policy import summarize_impressions
from backend.shared.ids import is_uuidv7, new_uuid


class TestContentImpressionRecord:
    def test_mints_uuidv7(self):
        impression = ContentImpression.record(placement_id=new_uuid(), duration_shown_seconds=10)
        assert is_uuidv7(impression.id)

    def test_validates_placement_id_as_uuid(self):
        with pytest.raises(ValueError):
            ContentImpression.record(placement_id="not-a-uuid", duration_shown_seconds=10)

    @pytest.mark.parametrize("duration", [-1, 1.5, True])
    def test_rejects_invalid_duration(self, duration):
        with pytest.raises(CustomerDisplayInvalidValueError):
            ContentImpression.record(placement_id=new_uuid(), duration_shown_seconds=duration)

    def test_zero_duration_is_allowed(self):
        impression = ContentImpression.record(placement_id=new_uuid(), duration_shown_seconds=0)
        assert impression.duration_shown_seconds == 0


class TestSummarizeImpressions:
    def test_empty_list_returns_zero_summary(self):
        summary = summarize_impressions([])
        assert summary.total_impressions == 0
        assert summary.total_duration_seconds == 0
        assert summary.average_duration_seconds == Decimal("0")

    def test_aggregates_count_and_total(self):
        placement_id = new_uuid()
        impressions = [
            ContentImpression.record(placement_id=placement_id, duration_shown_seconds=10),
            ContentImpression.record(placement_id=placement_id, duration_shown_seconds=20),
            ContentImpression.record(placement_id=placement_id, duration_shown_seconds=15),
        ]
        summary = summarize_impressions(impressions)
        assert summary.total_impressions == 3
        assert summary.total_duration_seconds == 45
        assert summary.average_duration_seconds == Decimal("15.00")

    def test_average_rounds_half_up(self):
        placement_id = new_uuid()
        impressions = [
            ContentImpression.record(placement_id=placement_id, duration_shown_seconds=1),
            ContentImpression.record(placement_id=placement_id, duration_shown_seconds=2),
        ]
        summary = summarize_impressions(impressions)
        assert summary.average_duration_seconds == Decimal("1.50")

    def test_single_impression(self):
        impression = ContentImpression.record(placement_id=new_uuid(), duration_shown_seconds=7)
        summary = summarize_impressions([impression])
        assert summary.total_impressions == 1
        assert summary.average_duration_seconds == Decimal("7.00")
