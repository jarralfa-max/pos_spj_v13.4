"""RecordContentImpressionUseCase — SET-18 cutover: the real recording
capability `ContentImpression`'s own docstring anticipated a "future
gateway consumer" would call. `sales_pos`'s ad-rotation timer
(`SalesPosWorkspace._on_ad_timer_tick`) is that consumer.
"""

from __future__ import annotations

from backend.domain.customer_display.entities.content_impression import ContentImpression
from backend.infrastructure.db.repositories.customer_display.content_impression_repository import (
    SqliteContentImpressionRepository,
)


class RecordContentImpressionUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._impressions = SqliteContentImpressionRepository(connection)

    def execute(self, *, placement_id: str, duration_shown_seconds: int) -> ContentImpression:
        impression = ContentImpression.record(
            placement_id=placement_id, duration_shown_seconds=duration_shown_seconds,
        )
        self._impressions.save(impression)
        self._conn.commit()
        return impression
