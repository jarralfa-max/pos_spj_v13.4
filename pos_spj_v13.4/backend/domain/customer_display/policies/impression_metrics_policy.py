"""ImpressionMetricsPolicy — SET-18 "Metrics": aggregates a
`CampaignPlacement`'s `ContentImpression` history into an
`ImpressionSummary`. Pure computation over already-recorded data — no I/O,
no assumption about how impressions were captured.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from backend.domain.customer_display.entities.content_impression import ContentImpression
from backend.domain.customer_display.value_objects.impression_summary import ImpressionSummary


def summarize_impressions(impressions: list[ContentImpression]) -> ImpressionSummary:
    if not impressions:
        return ImpressionSummary.zero()
    total_impressions = len(impressions)
    total_duration = sum(impression.duration_shown_seconds for impression in impressions)
    average = (Decimal(total_duration) / Decimal(total_impressions)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP,
    )
    return ImpressionSummary(
        total_impressions=total_impressions, total_duration_seconds=total_duration,
        average_duration_seconds=average,
    )
