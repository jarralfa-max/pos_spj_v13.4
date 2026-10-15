"""Attendance policy — punch sequencing, lateness and overtime rules."""

from __future__ import annotations

from datetime import date, datetime, timezone, tzinfo

from backend.domain.hr.entities import AttendanceWorkday, WorkShift
from backend.domain.hr.enums import PunchType
from backend.domain.hr.exceptions import (
    AttendanceAlreadyOpenError,
    AttendanceInvalidSequenceError,
    AttendanceMissingEntryError,
)


class AttendancePolicy:
    #: Horas máximas entre la entrada abierta y una salida para considerarla de
    #: la MISMA jornada (HR-13: turnos nocturnos que cruzan la medianoche).
    MAX_OPEN_WORKDAY_HOURS = 20

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
    def late_minutes(entry_at: datetime, shift: WorkShift | None, *,
                     work_date: date | None = None, tz: tzinfo | None = None) -> int:
        """Retardo contra el inicio del turno EN LA HORA LOCAL de la sucursal
        (HR-22): una entrada a las 15:00Z es 09:00 en la Ciudad de México."""
        if shift is None:
            return 0
        zone = tz or entry_at.tzinfo or timezone.utc
        local_entry = entry_at.astimezone(zone) if entry_at.tzinfo else entry_at.replace(tzinfo=zone)
        day = work_date or local_entry.date()
        scheduled = datetime.combine(day, shift.start_time, tzinfo=zone)
        delta = int((local_entry - scheduled).total_seconds() // 60)
        if delta <= shift.late_tolerance_minutes:
            return 0
        return delta

    @staticmethod
    def overtime_minutes(worked_minutes: int, shift: WorkShift | None) -> int:
        if shift is None:
            return 0
        return max(0, worked_minutes - shift.expected_minutes())


def _shift_expected_minutes(shift: WorkShift) -> int:
    return shift.expected_minutes()
