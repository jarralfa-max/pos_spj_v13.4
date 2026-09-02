"""SqliteContentImpressionRepository — persists `ContentImpression`
(SET-18). Implements
`backend.domain.customer_display.repository_ports.ContentImpressionRepositoryPort`.
Append-only — no ``get``/update, matching the entity's own "record, don't
mutate" shape.
"""

from __future__ import annotations

from backend.domain.customer_display.entities.content_impression import ContentImpression
from backend.infrastructure.db.repositories.customer_display.base import CustomerDisplayRepositoryBase

_COLS = "id, placement_id, duration_shown_seconds, displayed_at"


class SqliteContentImpressionRepository(CustomerDisplayRepositoryBase):
    def save(self, impression: ContentImpression) -> None:
        self._execute(
            f"INSERT INTO content_impressions ({_COLS}) VALUES (?,?,?,?)",
            self._params(impression),
        )

    def list_for_placement(self, placement_id: str) -> list[ContentImpression]:
        rows = self._query(
            f"SELECT {_COLS} FROM content_impressions WHERE placement_id=? ORDER BY displayed_at",
            (placement_id,),
        )
        return [self._hydrate(row) for row in rows]

    # helpers -----------------------------------------------------------------
    @staticmethod
    def _params(impression: ContentImpression) -> tuple:
        return (
            impression.id, impression.placement_id, impression.duration_shown_seconds,
            impression.displayed_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> ContentImpression:
        return ContentImpression(
            id=row["id"], placement_id=row["placement_id"],
            duration_shown_seconds=row["duration_shown_seconds"], displayed_at=row["displayed_at"],
        )
