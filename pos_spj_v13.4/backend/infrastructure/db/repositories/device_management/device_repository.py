"""SqliteDeviceRepository — persists `Device` (SET-7). Implements
`backend.domain.device_management.repository_ports.DeviceRepositoryPort`.
"""

from __future__ import annotations

from backend.domain.device_management.entities.device import Device
from backend.domain.device_management.enums import DeviceStatus
from backend.domain.device_management.value_objects.device_identifier import DeviceIdentifier
from backend.infrastructure.db.repositories.device_management.base import DeviceManagementRepositoryBase

_COLS = (
    "id, branch_id, profile_id, code, name, hardware_identifier, status, notes,"
    " blocked_reason, created_at, updated_at"
)


class SqliteDeviceRepository(DeviceManagementRepositoryBase):
    def save(self, device: Device) -> None:
        self._execute(
            f"INSERT INTO devices ({_COLS})"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET"
            " profile_id=excluded.profile_id, code=excluded.code, name=excluded.name,"
            " hardware_identifier=excluded.hardware_identifier, status=excluded.status,"
            " notes=excluded.notes, blocked_reason=excluded.blocked_reason,"
            " updated_at=excluded.updated_at",
            self._params(device),
        )

    def get(self, device_id: str) -> Device | None:
        row = self._query_one(f"SELECT {_COLS} FROM devices WHERE id=?", (device_id,))
        return self._hydrate(row) if row else None

    def get_by_code(self, code: str) -> Device | None:
        row = self._query_one(f"SELECT {_COLS} FROM devices WHERE code=?", (code,))
        return self._hydrate(row) if row else None

    def list_by_branch(self, branch_id: str) -> list[Device]:
        rows = self._query(f"SELECT {_COLS} FROM devices WHERE branch_id=? ORDER BY code", (branch_id,))
        return [self._hydrate(row) for row in rows]

    def list_active(self) -> list[Device]:
        rows = self._query(f"SELECT {_COLS} FROM devices WHERE status='ACTIVE' ORDER BY code")
        return [self._hydrate(row) for row in rows]

    def list_all(self) -> list[Device]:
        rows = self._query(f"SELECT {_COLS} FROM devices ORDER BY code")
        return [self._hydrate(row) for row in rows]

    # helpers -----------------------------------------------------------------
    @staticmethod
    def _params(device: Device) -> tuple:
        return (
            device.id, device.branch_id, device.profile_id, device.code, device.name,
            str(device.hardware_identifier) if device.hardware_identifier else None,
            device.status.value, device.notes, device.blocked_reason,
            device.created_at, device.updated_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> Device:
        return Device(
            id=row["id"], branch_id=row["branch_id"], profile_id=row["profile_id"], code=row["code"],
            name=row["name"],
            hardware_identifier=(
                DeviceIdentifier(row["hardware_identifier"]) if row["hardware_identifier"] else None
            ),
            status=DeviceStatus(row["status"]), notes=row["notes"] or "",
            blocked_reason=row["blocked_reason"], created_at=row["created_at"], updated_at=row["updated_at"],
        )
