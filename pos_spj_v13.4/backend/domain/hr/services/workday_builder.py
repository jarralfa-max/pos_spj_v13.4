"""Build calculated workday values from immutable punches."""

from __future__ import annotations

from backend.domain.hr.entities import AttendancePunch, AttendanceWorkday
from backend.domain.hr.enums import PunchType, WorkdayStatus
from backend.domain.hr.services.attendance_calculator import AttendanceCalculator


class WorkdayBuilder:
    def __init__(self, calculator: AttendanceCalculator | None = None) -> None:
        self._calculator = calculator or AttendanceCalculator()

    def build(self, punches: list[AttendancePunch], base: AttendanceWorkday) -> AttendanceWorkday:
        entries = [p.occurred_at for p in punches if p.punch_type == PunchType.ENTRY]
        exits = [p.occurred_at for p in punches if p.punch_type == PunchType.EXIT]
        base.first_entry_at = min(entries) if entries else None
        base.last_exit_at = max(exits) if exits else None
        base.worked_minutes = self._calculator.worked_minutes(base.first_entry_at, base.last_exit_at)
        if base.first_entry_at and base.last_exit_at:
            base.status = WorkdayStatus.COMPLETE
        elif base.first_entry_at:
            base.status = WorkdayStatus.MISSING_EXIT
        elif base.last_exit_at:
            base.status = WorkdayStatus.MISSING_ENTRY
        else:
            base.status = WorkdayStatus.ABSENT
        return base
