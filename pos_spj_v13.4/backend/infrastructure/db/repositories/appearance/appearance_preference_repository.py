"""SqliteAppearancePreferenceRepository — persists `AppearancePreference`
(SET-22). Implements
`backend.domain.appearance.repository_ports.AppearancePreferenceRepositoryPort`.
"""

from __future__ import annotations

from backend.domain.appearance.entities.appearance_preference import AppearancePreference
from backend.domain.appearance.enums import AppearanceScopeType, DensityLevel
from backend.infrastructure.db.repositories.appearance.base import AppearanceRepositoryBase

_COLS = "id, scope_type, scope_id, theme_id, density_level, active, created_at, updated_at"


class SqliteAppearancePreferenceRepository(AppearanceRepositoryBase):
    def save(self, preference: AppearancePreference) -> None:
        self._execute(
            f"INSERT INTO appearance_preferences ({_COLS})"
            " VALUES (?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET"
            " theme_id=excluded.theme_id, density_level=excluded.density_level,"
            " active=excluded.active, updated_at=excluded.updated_at",
            self._params(preference),
        )

    def get(self, preference_id: str) -> AppearancePreference | None:
        row = self._query_one(f"SELECT {_COLS} FROM appearance_preferences WHERE id=?", (preference_id,))
        return self._hydrate(row) if row else None

    def list_active(self) -> list[AppearancePreference]:
        rows = self._query(f"SELECT {_COLS} FROM appearance_preferences WHERE active=1")
        return [self._hydrate(row) for row in rows]

    def list_all(self) -> list[AppearancePreference]:
        rows = self._query(f"SELECT {_COLS} FROM appearance_preferences")
        return [self._hydrate(row) for row in rows]

    # helpers -----------------------------------------------------------------
    @staticmethod
    def _params(preference: AppearancePreference) -> tuple:
        return (
            preference.id, preference.scope_type.value, preference.scope_id, preference.theme_id,
            preference.density_level.value, int(preference.active), preference.created_at,
            preference.updated_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> AppearancePreference:
        return AppearancePreference(
            id=row["id"], scope_type=AppearanceScopeType(row["scope_type"]), scope_id=row["scope_id"],
            theme_id=row["theme_id"], density_level=DensityLevel(row["density_level"]),
            active=bool(row["active"]), created_at=row["created_at"], updated_at=row["updated_at"],
        )
