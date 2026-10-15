"""AttendanceCalculator — aggregate metrics over a set of workdays."""

from __future__ import annotations

from dataclasses import dataclass

from backend.domain.hr.entities import AttendanceWorkday
from backend.domain.hr.enums import WorkdayStatus

#: Jornadas terminadas: completa o completa por un ajuste aprobado. La
#: completitud no se confunde con "fue ajustada" (auditoría HR-17: una jornada
#: ADJUSTED de 480 minutos no contaba como presente).
FINISHED_STATUSES = frozenset({WorkdayStatus.COMPLETE, WorkdayStatus.ADJUSTED})
#: Jornadas que esperan resolución (entrada sin salida, incidencia).
PENDING_STATUSES = frozenset({WorkdayStatus.OPEN, WorkdayStatus.INCIDENT})


@dataclass(frozen=True, slots=True)
class AttendanceSummary:
    worked_minutes: int
    late_minutes: int
    overtime_minutes: int
    present_days: int
    incident_days: int
    pending_days: int = 0


class AttendanceCalculator:
    def summarize(self, workdays: list[AttendanceWorkday]) -> AttendanceSummary:
        worked = sum(w.worked_minutes for w in workdays)
        late = sum(w.late_minutes for w in workdays)
        overtime = sum(w.overtime_minutes for w in workdays)
        present = sum(1 for w in workdays if w.status in FINISHED_STATUSES)
        incidents = sum(1 for w in workdays if w.status is WorkdayStatus.INCIDENT)
        pending = sum(1 for w in workdays if w.status in PENDING_STATUSES)
        return AttendanceSummary(worked, late, overtime, present, incidents, pending)
