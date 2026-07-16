"""Attendance policy — punch sequencing, lateness and overtime rules."""

from __future__ import annotations

from datetime import datetime, time

from backend.domain.hr.entities import AttendanceWorkday, WorkShift
from backend.domain.hr.enums import PunchType
from backend.domain.hr.exceptions import (
    AttendanceAlreadyOpenError,
    AttendanceInvalidSequenceError,
    AttendanceMissingEntryError,
)


class AttendancePolicy:
    def enforce_entry(self, workday: AttendanceWorkday) -> None:
        """An entry cannot open on a workday that already has an open entry."""
        if workday.has_open_entry():
            raise AttendanceAlreadyOpenError(
                f"El empleado {workday.employee_id} ya tiene una entrada abierta"
            )

    def enforce_exit(self, workday: AttendanceWorkday) -> None:
        if workday.first_entry_at is None:
            raise AttendanceMissingEntryError(
                f"No existe entrada abierta para el empleado {workday.employee_id}"
            )
        if workday.last_exit_at is not None:
            raise AttendanceInvalidSequenceError("La jornada ya tiene salida registrada")

    def enforce_sequence(self, previous: PunchType | None, incoming: PunchType) -> None:
        if previous is None and incoming is PunchType.EXIT:
            raise AttendanceMissingEntryError("Una salida requiere una entrada previa")
        if previous is incoming:
            raise AttendanceInvalidSequenceError(
                f"Marcación fuera de secuencia: {previous} → {incoming}"
            )

    @staticmethod
    def late_minutes(entry_at: datetime, shift: WorkShift | None) -> int:
        if shift is None:
            return 0
        scheduled = datetime.combine(entry_at.date(), shift.start_time,
                                     tzinfo=entry_at.tzinfo)
        delta = int((entry_at - scheduled).total_seconds() // 60)
        if delta <= shift.late_tolerance_minutes:
            return 0
        return delta

    @staticmethod
    def overtime_minutes(worked_minutes: int, shift: WorkShift | None) -> int:
        if shift is None:
            return 0
        expected = _shift_expected_minutes(shift)
        return max(0, worked_minutes - expected)


def _shift_expected_minutes(shift: WorkShift) -> int:
    start = shift.start_time.hour * 60 + shift.start_time.minute
    end = shift.end_time.hour * 60 + shift.end_time.minute
    if shift.crosses_midnight:
        end += 24 * 60
    return max(0, end - start - shift.break_minutes)
