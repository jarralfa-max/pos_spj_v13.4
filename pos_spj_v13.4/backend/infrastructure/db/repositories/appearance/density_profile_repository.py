"""SqliteDensityProfileRepository — persists `DensityProfile` (SET-22).
Implements
`backend.domain.appearance.repository_ports.DensityProfileRepositoryPort`.
`scale_factor` is stored as TEXT and hydrated back through `Decimal(str)`
— never `float` — to stay precision-safe (mirrors how the rest of this
codebase persists Decimal-typed business values).
"""

from __future__ import annotations

from decimal import Decimal

from backend.domain.appearance.entities.density_profile import DensityProfile
from backend.domain.appearance.enums import DensityLevel
from backend.infrastructure.db.repositories.appearance.base import AppearanceRepositoryBase

_COLS = (
    "id, level, name, scale_factor, control_height_px, touch_target_px, spacing_unit_px, active,"
    " created_at, updated_at"
)


class SqliteDensityProfileRepository(AppearanceRepositoryBase):
    def save(self, profile: DensityProfile) -> None:
        self._execute(
            f"INSERT INTO density_profiles ({_COLS})"
            " VALUES (?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET"
            " name=excluded.name, scale_factor=excluded.scale_factor,"
            " control_height_px=excluded.control_height_px, touch_target_px=excluded.touch_target_px,"
            " spacing_unit_px=excluded.spacing_unit_px, active=excluded.active,"
            " updated_at=excluded.updated_at",
            self._params(profile),
        )

    def get(self, profile_id: str) -> DensityProfile | None:
        row = self._query_one(f"SELECT {_COLS} FROM density_profiles WHERE id=?", (profile_id,))
        return self._hydrate(row) if row else None

    def get_by_level(self, level: DensityLevel) -> DensityProfile | None:
        row = self._query_one(f"SELECT {_COLS} FROM density_profiles WHERE level=?", (level.value,))
        return self._hydrate(row) if row else None

    def list_active(self) -> list[DensityProfile]:
        rows = self._query(f"SELECT {_COLS} FROM density_profiles WHERE active=1 ORDER BY level")
        return [self._hydrate(row) for row in rows]

    def list_all(self) -> list[DensityProfile]:
        rows = self._query(f"SELECT {_COLS} FROM density_profiles ORDER BY level")
        return [self._hydrate(row) for row in rows]

    # helpers -----------------------------------------------------------------
    @staticmethod
    def _params(profile: DensityProfile) -> tuple:
        return (
            profile.id, profile.level.value, profile.name, str(profile.scale_factor),
            profile.control_height_px, profile.touch_target_px, profile.spacing_unit_px,
            int(profile.active), profile.created_at, profile.updated_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> DensityProfile:
        return DensityProfile(
            id=row["id"], level=DensityLevel(row["level"]), name=row["name"],
            scale_factor=Decimal(row["scale_factor"]), control_height_px=row["control_height_px"],
            touch_target_px=row["touch_target_px"], spacing_unit_px=row["spacing_unit_px"],
            active=bool(row["active"]), created_at=row["created_at"], updated_at=row["updated_at"],
        )
