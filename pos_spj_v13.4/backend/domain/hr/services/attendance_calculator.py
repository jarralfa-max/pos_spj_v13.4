"""AttendanceCalculator — aggregate metrics over a set of workdays."""

from __future__ import annotations

from dataclasses import dataclass

from backend.domain.hr.entities import AttendanceWorkday
from backend.domain.hr.enums import WorkdayStatus


@dataclass(frozen=True, slots=True)
class AttendanceSummary:
    worked_minutes: int
    late_minutes: int
    overtime_minutes: int
    present_days: int
    incident_days: int


class AttendanceCalculator:
    def summarize(self, workdays: list[AttendanceWorkday]) -> AttendanceSummary:
        worked = sum(w.worked_minutes for w in workdays)
        late = sum(w.late_minutes for w in workdays)
        overtime = sum(w.overtime_minutes for w in workdays)
        present = sum(1 for w in workdays if w.status is WorkdayStatus.COMPLETE)
        incidents = sum(1 for w in workdays if w.status is WorkdayStatus.INCIDENT)
        return AttendanceSummary(worked, late, overtime, present, incidents)
