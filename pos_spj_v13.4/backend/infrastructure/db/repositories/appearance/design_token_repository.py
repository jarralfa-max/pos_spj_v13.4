"""SqliteDesignTokenRepository — persists `DesignToken` (SET-22).
Implements
`backend.domain.appearance.repository_ports.DesignTokenRepositoryPort`.
"""

from __future__ import annotations

from backend.domain.appearance.entities.design_token import DesignToken
from backend.domain.appearance.enums import TokenCategory
from backend.infrastructure.db.repositories.appearance.base import AppearanceRepositoryBase

_COLS = "id, theme_id, token_key, category, token_value, created_at, updated_at"


class SqliteDesignTokenRepository(AppearanceRepositoryBase):
    def save(self, token: DesignToken) -> None:
        self._execute(
            f"INSERT INTO design_tokens ({_COLS})"
            " VALUES (?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET"
            " token_value=excluded.token_value, updated_at=excluded.updated_at",
            self._params(token),
        )

    def get(self, token_id: str) -> DesignToken | None:
        row = self._query_one(f"SELECT {_COLS} FROM design_tokens WHERE id=?", (token_id,))
        return self._hydrate(row) if row else None

    def list_for_theme(self, theme_id: str) -> list[DesignToken]:
        rows = self._query(
            f"SELECT {_COLS} FROM design_tokens WHERE theme_id IS NULL OR theme_id=? ORDER BY token_key",
            (theme_id,),
        )
        return [self._hydrate(row) for row in rows]

    # helpers -----------------------------------------------------------------
    @staticmethod
    def _params(token: DesignToken) -> tuple:
        return (
            token.id, token.theme_id, token.token_key, token.category.value, token.token_value,
            token.created_at, token.updated_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> DesignToken:
        return DesignToken(
            id=row["id"], theme_id=row["theme_id"], token_key=row["token_key"],
            category=TokenCategory(row["category"]), token_value=row["token_value"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )
