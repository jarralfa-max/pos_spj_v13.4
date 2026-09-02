"""SqliteFeatureFlagRepository — persists `FeatureFlag` (SET-21).
Implements
`backend.domain.feature_flags.repository_ports.FeatureFlagRepositoryPort`.
"""

from __future__ import annotations

from backend.domain.feature_flags.entities.feature_flag import FeatureFlag
from backend.infrastructure.db.repositories.feature_flags.base import FeatureFlagsRepositoryBase

_COLS = "id, code, name, description, default_enabled, active, created_at, updated_at"


class SqliteFeatureFlagRepository(FeatureFlagsRepositoryBase):
    def save(self, flag: FeatureFlag) -> None:
        self._execute(
            f"INSERT INTO ff_flags ({_COLS})"
            " VALUES (?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET"
            " name=excluded.name, description=excluded.description,"
            " default_enabled=excluded.default_enabled, active=excluded.active,"
            " updated_at=excluded.updated_at",
            self._params(flag),
        )

    def get(self, flag_id: str) -> FeatureFlag | None:
        row = self._query_one(f"SELECT {_COLS} FROM ff_flags WHERE id=?", (flag_id,))
        return self._hydrate(row) if row else None

    def get_by_code(self, code: str) -> FeatureFlag | None:
        row = self._query_one(f"SELECT {_COLS} FROM ff_flags WHERE code=?", (code.strip(),))
        return self._hydrate(row) if row else None

    def list_active(self) -> list[FeatureFlag]:
        rows = self._query(f"SELECT {_COLS} FROM ff_flags WHERE active=1 ORDER BY code")
        return [self._hydrate(row) for row in rows]

    def list_all(self) -> list[FeatureFlag]:
        rows = self._query(f"SELECT {_COLS} FROM ff_flags ORDER BY code")
        return [self._hydrate(row) for row in rows]

    # helpers -----------------------------------------------------------------
    @staticmethod
    def _params(flag: FeatureFlag) -> tuple:
        return (
            flag.id, flag.code, flag.name, flag.description, int(flag.default_enabled), int(flag.active),
            flag.created_at, flag.updated_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> FeatureFlag:
        return FeatureFlag(
            id=row["id"], code=row["code"], name=row["name"], description=row["description"] or "",
            default_enabled=bool(row["default_enabled"]), active=bool(row["active"]),
            created_at=row["created_at"], updated_at=row["updated_at"],
        )
