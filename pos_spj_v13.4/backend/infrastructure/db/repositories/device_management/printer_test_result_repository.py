"""SqlitePrinterTestResultRepository — persists `PrinterTestResult`
(SET-8). Implements
`backend.domain.device_management.repository_ports.PrinterTestResultRepositoryPort`.
Append-only: no update path, `save()` always inserts.
"""

from __future__ import annotations

from backend.domain.device_management.entities.printer_test_result import PrinterTestResult
from backend.infrastructure.db.repositories.device_management.base import DeviceManagementRepositoryBase

_COLS = "id, device_id, success, message, tested_by_user_id, tested_at"


class SqlitePrinterTestResultRepository(DeviceManagementRepositoryBase):
    def save(self, result: PrinterTestResult) -> None:
        self._execute(
            f"INSERT INTO printer_test_results ({_COLS}) VALUES (?,?,?,?,?,?)",
            self._params(result),
        )

    def list_for_device(self, device_id: str) -> list[PrinterTestResult]:
        rows = self._query(
            f"SELECT {_COLS} FROM printer_test_results WHERE device_id=? ORDER BY tested_at DESC",
            (device_id,),
        )
        return [self._hydrate(row) for row in rows]

    # helpers -----------------------------------------------------------------
    @staticmethod
    def _params(result: PrinterTestResult) -> tuple:
        return (
            result.id, result.device_id, int(result.success), result.message,
            result.tested_by_user_id, result.tested_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> PrinterTestResult:
        return PrinterTestResult(
            id=row["id"], device_id=row["device_id"], success=bool(row["success"]),
            message=row["message"] or "", tested_by_user_id=row["tested_by_user_id"],
            tested_at=row["tested_at"],
        )
