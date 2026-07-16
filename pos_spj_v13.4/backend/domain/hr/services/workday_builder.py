"""WorkdayBuilder — recomputes a workday from its immutable punches."""

from __future__ import annotations

from datetime import datetime

from backend.domain.hr.entities import AttendancePunch, AttendanceWorkday, WorkShift
from backend.domain.hr.enums import (
    AttendanceIncidentType,
    PunchType,
    WorkdayStatus,
)
from backend.domain.hr.policies.attendance_policy import AttendancePolicy


class WorkdayBuilder:
    """Pure recalculation of a workday's derived fields from ordered punches."""

    def __init__(self) -> None:
        self._policy = AttendancePolicy()

    def rebuild(self, workday: AttendanceWorkday, punches: list[AttendancePunch],
                shift: WorkShift | None = None) -> AttendanceWorkday:
        ordered = sorted(punches, key=lambda p: p.occurred_at)
        entries = [p for p in ordered if p.punch_type is PunchType.ENTRY]
        exits = [p for p in ordered if p.punch_type is PunchType.EXIT]

        workday.first_entry_at = entries[0].occurred_at if entries else None
        workday.last_exit_at = exits[-1].occurred_at if exits else None
        workday.calculation_version += 1

        if not entries and not exits:
            workday.status = WorkdayStatus.OPEN
            workday.worked_minutes = 0
            workday.late_minutes = 0
            workday.overtime_minutes = 0
            return workday

        if entries and not exits:
            workday.status = WorkdayStatus.OPEN
            workday.worked_minutes = 0
        elif exits and not entries:
            workday.status = WorkdayStatus.INCIDENT
            workday.incident_type = AttendanceIncidentType.MISSING_ENTRY
            workday.worked_minutes = 0
        else:
            worked = int((workday.last_exit_at - workday.first_entry_at).total_seconds() // 60)
            workday.worked_minutes = max(0, worked)
            workday.status = WorkdayStatus.COMPLETE

        if workday.first_entry_at is not None:
            workday.late_minutes = self._policy.late_minutes(workday.first_entry_at, shift)
        if workday.status is WorkdayStatus.COMPLETE:
            workday.overtime_minutes = self._policy.overtime_minutes(
                workday.worked_minutes, shift)
        return workday

    @staticmethod
    def build_incident(workday: AttendanceWorkday,
                       incident_type: AttendanceIncidentType) -> AttendanceWorkday:
        workday.status = WorkdayStatus.INCIDENT
        workday.incident_type = incident_type
        return workday
