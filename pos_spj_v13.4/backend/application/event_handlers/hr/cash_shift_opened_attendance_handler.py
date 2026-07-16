"""Register HR entry punches from canonical CASH_SHIFT_OPENED events."""

from __future__ import annotations

from datetime import datetime

from backend.application.commands.attendance_commands import RegisterAttendancePunchCommand
from backend.application.use_cases.hr.register_attendance_punch_use_case import RegisterAttendancePunchUseCase
from backend.domain.hr.enums import AttendanceSource, PunchType


class CashShiftOpenedAttendanceHandler:
    def __init__(self, use_case: RegisterAttendancePunchUseCase, *, enabled: bool = True) -> None:
        self._use_case = use_case
        self._enabled = enabled

    def handle(self, payload: dict) -> None:
        if not self._enabled:
            return
        self._use_case.execute(
            RegisterAttendancePunchCommand(
                operation_id=str(payload["operation_id"]),
                branch_id=str(payload["branch_id"]),
                user_id=str(payload["user_id"]),
                employee_id=str(payload["employee_id"]),
                punch_type=PunchType.ENTRY,
                occurred_at=datetime.fromisoformat(str(payload["opened_at"])),
                timezone=str(payload.get("timezone") or "America/Mexico_City"),
                source=AttendanceSource.CASH_REGISTER,
                source_reference_id=str(payload["shift_id"]),
                notes="Entrada generada por apertura de caja POS.",
            )
        )
