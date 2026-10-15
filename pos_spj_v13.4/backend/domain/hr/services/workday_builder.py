"""WorkdayBuilder — recomputes a workday from its immutable punches.

Auditoría RRHH cebf67a:

* HR-14 — la jornada se calcula por SEGMENTOS emparejados entrada→salida y se
  suman sus duraciones; antes era ``última salida − primera entrada`` y contaba
  la comida de 12 a 14 como trabajada. Una salida sin segmento abierto no
  amplía la jornada: queda como incidencia ``OUT_OF_SEQUENCE``.
* HR-15 — el descanso configurado del turno es NO pagado: se descuenta del
  trabajado tanto como del esperado (sin descontarlo dos veces si el empleado
  ya marcó su salida a comer).
* HR-17 — los ajustes APROBADOS son una capa efectiva sobre las marcaciones
  inmutables: cualquier recálculo los vuelve a aplicar, en vez de borrarlos.
* HR-22 — el retardo se mide en la hora local de la sucursal.
"""

from __future__ import annotations

from datetime import datetime, tzinfo

from backend.domain.hr.entities import AttendancePunch, AttendanceWorkday, WorkShift
from backend.domain.hr.enums import (
    AdjustmentStatus,
    AttendanceIncidentType,
    PunchType,
    WorkdayStatus,
)
from backend.domain.hr.policies.attendance_policy import AttendancePolicy

#: Campos que un ajuste de asistencia puede corregir.
ADJUSTABLE_FIELDS = ("first_entry_at", "last_exit_at")


class WorkdayBuilder:
    """Pure recalculation of a workday's derived fields from ordered punches."""

    def __init__(self) -> None:
        self._policy = AttendancePolicy()

    def rebuild(self, workday: AttendanceWorkday, punches: list[AttendancePunch],
                shift: WorkShift | None = None, *, adjustments=(),
                tz: tzinfo | None = None) -> AttendanceWorkday:
        marks = [(p.punch_type, p.occurred_at) for p in punches]
        applied = self._apply_adjustments(marks, adjustments)
        marks.sort(key=lambda mark: mark[1])

        segments: list[tuple[datetime, datetime]] = []
        open_entry: datetime | None = None
        incident: AttendanceIncidentType | None = None
        for kind, moment in marks:
            if kind is PunchType.ENTRY:
                if open_entry is None:
                    open_entry = moment
                # una segunda entrada con el segmento abierto se ignora: la
                # primera es la evidencia (el caso de uso ya no la duplica)
            elif open_entry is not None:
                segments.append((open_entry, moment))
                open_entry = None
            elif not segments:
                incident = incident or AttendanceIncidentType.MISSING_ENTRY
            else:
                incident = AttendanceIncidentType.OUT_OF_SEQUENCE

        workday.calculation_version += 1
        workday.first_entry_at = segments[0][0] if segments else open_entry
        workday.last_exit_at = segments[-1][1] if segments else None
        if open_entry is not None and segments:
            # segmento abierto después de uno cerrado: la jornada sigue abierta
            workday.last_exit_at = None
        workday.incident_type = None

        gross = sum(int((end - start).total_seconds() // 60) for start, end in segments)
        gaps = sum(int((segments[i + 1][0] - segments[i][1]).total_seconds() // 60)
                   for i in range(len(segments) - 1))
        unpaid_break = 0
        if shift is not None and shift.break_minutes and segments:
            unpaid_break = min(gross, max(0, shift.break_minutes - gaps))
        workday.worked_minutes = max(0, gross - unpaid_break)
        workday.late_minutes = 0
        workday.overtime_minutes = 0

        if not marks:
            workday.status = WorkdayStatus.OPEN
            return workday
        if incident is not None:
            workday.status = WorkdayStatus.INCIDENT
            workday.incident_type = incident
        elif open_entry is not None:
            workday.status = WorkdayStatus.OPEN
        else:
            workday.status = WorkdayStatus.ADJUSTED if applied else WorkdayStatus.COMPLETE

        if workday.first_entry_at is not None:
            workday.late_minutes = self._policy.late_minutes(
                workday.first_entry_at, shift, work_date=workday.work_date, tz=tz)
        if workday.status in (WorkdayStatus.COMPLETE, WorkdayStatus.ADJUSTED):
            workday.overtime_minutes = self._policy.overtime_minutes(
                workday.worked_minutes, shift)
        return workday

    @staticmethod
    def _apply_adjustments(marks: list, adjustments) -> bool:
        """Reemplaza la primera entrada / la última salida por el valor
        aprobado, o la agrega si faltaba (salida olvidada)."""
        applied = False
        for adjustment in adjustments or ():
            if getattr(adjustment, "status", AdjustmentStatus.APPROVED) is not AdjustmentStatus.APPROVED:
                continue
            if adjustment.field_name not in ADJUSTABLE_FIELDS:
                continue
            moment = datetime.fromisoformat(adjustment.requested_value)
            kind = PunchType.ENTRY if adjustment.field_name == "first_entry_at" else PunchType.EXIT
            positions = [i for i, (k, _) in enumerate(sorted(marks, key=lambda m: m[1]))
                         if k is kind]
            ordered = sorted(marks, key=lambda m: m[1])
            if positions:
                index = positions[0] if kind is PunchType.ENTRY else positions[-1]
                ordered[index] = (kind, moment)
            else:
                ordered.append((kind, moment))
            marks[:] = ordered
            applied = True
        return applied

    @staticmethod
    def build_incident(workday: AttendanceWorkday,
                       incident_type: AttendanceIncidentType) -> AttendanceWorkday:
        workday.status = WorkdayStatus.INCIDENT
        workday.incident_type = incident_type
        return workday
