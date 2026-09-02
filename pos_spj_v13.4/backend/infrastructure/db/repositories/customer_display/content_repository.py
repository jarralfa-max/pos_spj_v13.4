"""SqliteContentRepository — persists `Content` (SET-18). Implements
`backend.domain.customer_display.repository_ports.ContentRepositoryPort`.
"""

from __future__ import annotations

from backend.domain.customer_display.entities.content import Content
from backend.domain.customer_display.enums import ContentType
from backend.infrastructure.db.repositories.customer_display.base import CustomerDisplayRepositoryBase

_COLS = "id, title, content_type, body, duration_seconds, active, created_at, updated_at"


class SqliteContentRepository(CustomerDisplayRepositoryBase):
    def save(self, content: Content) -> None:
        self._execute(
            f"INSERT INTO display_content ({_COLS})"
            " VALUES (?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET"
            " title=excluded.title, body=excluded.body, duration_seconds=excluded.duration_seconds,"
            " active=excluded.active, updated_at=excluded.updated_at",
            self._params(content),
        )

    def get(self, content_id: str) -> Content | None:
        row = self._query_one(f"SELECT {_COLS} FROM display_content WHERE id=?", (content_id,))
        return self._hydrate(row) if row else None

    def list_active(self) -> list[Content]:
        rows = self._query(f"SELECT {_COLS} FROM display_content WHERE active=1 ORDER BY title")
        return [self._hydrate(row) for row in rows]

    def list_all(self) -> list[Content]:
        rows = self._query(f"SELECT {_COLS} FROM display_content ORDER BY title")
        return [self._hydrate(row) for row in rows]

    # helpers -----------------------------------------------------------------
    @staticmethod
    def _params(content: Content) -> tuple:
        return (
            content.id, content.title, content.content_type.value, content.body,
            content.duration_seconds, int(content.active), content.created_at, content.updated_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> Content:
        return Content(
            id=row["id"], title=row["title"], content_type=ContentType(row["content_type"]),
            body=row["body"], duration_seconds=row["duration_seconds"], active=bool(row["active"]),
            created_at=row["created_at"], updated_at=row["updated_at"],
        )
