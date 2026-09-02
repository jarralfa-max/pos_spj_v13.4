"""SqliteWorkstationRepository — persists `Workstation` (SET-6).
Implements
`backend.domain.settings.repository_ports.WorkstationRepositoryPort`.
"""

from __future__ import annotations

from backend.domain.settings.entities.workstation import Workstation
from backend.domain.settings.enums import WorkstationStatus, WorkstationType
from backend.infrastructure.db.repositories.settings.base import SettingsRepositoryBase

_COLS = (
    "id, branch_id, code, name, workstation_type, device_identifier, operating_system,"
    " application_version, status, offline_enabled, last_seen_at, blocked_reason,"
    " created_at, updated_at"
)


class SqliteWorkstationRepository(SettingsRepositoryBase):
    def save(self, workstation: Workstation) -> None:
        self._execute(
            f"INSERT INTO workstations ({_COLS})"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET"
            " code=excluded.code, name=excluded.name, workstation_type=excluded.workstation_type,"
            " device_identifier=excluded.device_identifier,"
            " operating_system=excluded.operating_system,"
            " application_version=excluded.application_version, status=excluded.status,"
            " offline_enabled=excluded.offline_enabled, last_seen_at=excluded.last_seen_at,"
            " blocked_reason=excluded.blocked_reason, updated_at=excluded.updated_at",
            self._params(workstation),
        )

    def get(self, workstation_id: str) -> Workstation | None:
        row = self._query_one(f"SELECT {_COLS} FROM workstations WHERE id=?", (workstation_id,))
        return self._hydrate(row) if row else None

    def get_by_code(self, code: str) -> Workstation | None:
        row = self._query_one(f"SELECT {_COLS} FROM workstations WHERE code=?", (code,))
        return self._hydrate(row) if row else None

    def list_by_branch(self, branch_id: str) -> list[Workstation]:
        rows = self._query(
            f"SELECT {_COLS} FROM workstations WHERE branch_id=? ORDER BY code", (branch_id,),
        )
        return [self._hydrate(row) for row in rows]

    def list_active(self) -> list[Workstation]:
        rows = self._query(f"SELECT {_COLS} FROM workstations WHERE status='ACTIVE' ORDER BY code")
        return [self._hydrate(row) for row in rows]

    def list_all(self) -> list[Workstation]:
        rows = self._query(f"SELECT {_COLS} FROM workstations ORDER BY code")
        return [self._hydrate(row) for row in rows]

    # helpers -----------------------------------------------------------------
    @staticmethod
    def _params(workstation: Workstation) -> tuple:
        return (
            workstation.id, workstation.branch_id, workstation.code, workstation.name,
            workstation.workstation_type.value, workstation.device_identifier,
            workstation.operating_system, workstation.application_version,
            workstation.status.value, int(workstation.offline_enabled),
            workstation.last_seen_at, workstation.blocked_reason,
            workstation.created_at, workstation.updated_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> Workstation:
        return Workstation(
            id=row["id"], branch_id=row["branch_id"], code=row["code"], name=row["name"],
            workstation_type=WorkstationType(row["workstation_type"]),
            device_identifier=row["device_identifier"] or "",
            operating_system=row["operating_system"] or "",
            application_version=row["application_version"] or "",
            status=WorkstationStatus(row["status"]), offline_enabled=bool(row["offline_enabled"]),
            last_seen_at=row["last_seen_at"], blocked_reason=row["blocked_reason"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )
