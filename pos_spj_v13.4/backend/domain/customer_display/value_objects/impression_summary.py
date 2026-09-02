"""ImpressionSummary — SET-18 "Metrics": the aggregate a caller actually
wants from a `CampaignPlacement`'s `ContentImpression` history — count
and total/average seconds shown. Decimal for the average (never float,
same discipline as every other bounded context in this refactor).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ImpressionSummary:
    total_impressions: int
    total_duration_seconds: int
    average_duration_seconds: Decimal

    @classmethod
    def zero(cls) -> "ImpressionSummary":
        return cls(total_impressions=0, total_duration_seconds=0, average_duration_seconds=Decimal("0"))
