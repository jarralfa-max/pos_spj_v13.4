"""SqliteThemeRepository — persists `Theme` (SET-22).
Implements
`backend.domain.appearance.repository_ports.ThemeRepositoryPort`.
"""

from __future__ import annotations

from backend.domain.appearance.entities.theme import Theme
from backend.domain.appearance.enums import ThemeMode
from backend.infrastructure.db.repositories.appearance.base import AppearanceRepositoryBase

_COLS = "id, code, name, mode, active, is_default, created_at, updated_at"


class SqliteThemeRepository(AppearanceRepositoryBase):
    def save(self, theme: Theme) -> None:
        self._execute(
            f"INSERT INTO themes ({_COLS})"
            " VALUES (?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET"
            " name=excluded.name, mode=excluded.mode, active=excluded.active,"
            " is_default=excluded.is_default, updated_at=excluded.updated_at",
            self._params(theme),
        )

    def get(self, theme_id: str) -> Theme | None:
        row = self._query_one(f"SELECT {_COLS} FROM themes WHERE id=?", (theme_id,))
        return self._hydrate(row) if row else None

    def get_by_code(self, code: str) -> Theme | None:
        row = self._query_one(f"SELECT {_COLS} FROM themes WHERE code=?", (code.strip(),))
        return self._hydrate(row) if row else None

    def get_default(self) -> Theme | None:
        row = self._query_one(f"SELECT {_COLS} FROM themes WHERE is_default=1")
        return self._hydrate(row) if row else None

    def list_active(self) -> list[Theme]:
        rows = self._query(f"SELECT {_COLS} FROM themes WHERE active=1 ORDER BY code")
        return [self._hydrate(row) for row in rows]

    def list_all(self) -> list[Theme]:
        rows = self._query(f"SELECT {_COLS} FROM themes ORDER BY code")
        return [self._hydrate(row) for row in rows]

    # helpers -----------------------------------------------------------------
    @staticmethod
    def _params(theme: Theme) -> tuple:
        return (
            theme.id, theme.code, theme.name, theme.mode.value, int(theme.active), int(theme.is_default),
            theme.created_at, theme.updated_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> Theme:
        return Theme(
            id=row["id"], code=row["code"], name=row["name"], mode=ThemeMode(row["mode"]),
            active=bool(row["active"]), is_default=bool(row["is_default"]), created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
