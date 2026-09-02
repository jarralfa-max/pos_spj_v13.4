"""SqliteDeviceTestResultRepository — persists `DeviceTestResult`
(SET-9). Implements
`backend.domain.device_management.repository_ports.DeviceTestResultRepositoryPort`.
Append-only: no update path, `save()` always inserts.
"""

from __future__ import annotations

from backend.domain.device_management.entities.device_test_result import DeviceTestResult
from backend.infrastructure.db.repositories.device_management.base import DeviceManagementRepositoryBase

_COLS = "id, device_id, test_type, success, message, tested_by_user_id, tested_at"


class SqliteDeviceTestResultRepository(DeviceManagementRepositoryBase):
    def save(self, result: DeviceTestResult) -> None:
        self._execute(
            f"INSERT INTO device_test_results ({_COLS}) VALUES (?,?,?,?,?,?,?)",
            self._params(result),
        )

    def list_for_device(self, device_id: str) -> list[DeviceTestResult]:
        rows = self._query(
            f"SELECT {_COLS} FROM device_test_results WHERE device_id=? ORDER BY tested_at DESC",
            (device_id,),
        )
        return [self._hydrate(row) for row in rows]

    # helpers -----------------------------------------------------------------
    @staticmethod
    def _params(result: DeviceTestResult) -> tuple:
        return (
            result.id, result.device_id, result.test_type, int(result.success), result.message,
            result.tested_by_user_id, result.tested_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> DeviceTestResult:
        return DeviceTestResult(
            id=row["id"], device_id=row["device_id"], test_type=row["test_type"],
            success=bool(row["success"]), message=row["message"] or "",
            tested_by_user_id=row["tested_by_user_id"], tested_at=row["tested_at"],
        )
