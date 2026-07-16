"""Attendance repositories — immutable punches, calculated workdays, adjustments."""

from __future__ import annotations

from datetime import date, datetime

from backend.domain.hr.entities import (
    AttendanceAdjustment,
    AttendancePunch,
    AttendanceWorkday,
)
from backend.domain.hr.enums import (
    AdjustmentStatus,
    AttendanceIncidentType,
    AttendanceSource,
    PunchType,
    WorkdayStatus,
)
from backend.infrastructure.db.repositories.hr.base import HRRepositoryBase

_PUNCH_COLS = (
    "id, employee_id, branch_id, workday_id, punch_type, occurred_at, timezone_name,"
    " source, source_reference_id, device_id, registered_by_user_id, operation_id,"
    " notes, created_at"
)
_WD_COLS = (
    "id, employee_id, branch_id, work_date, scheduled_shift_id, first_entry_at,"
    " last_exit_at, worked_minutes, late_minutes, overtime_minutes, status,"
    " incident_type, calculation_version, created_at, updated_at"
)
_ADJ_COLS = (
    "id, employee_id, workday_id, original_punch_id, field_name, previous_value,"
    " requested_value, reason, requested_by_user_id, approved_by_user_id, status,"
    " operation_id, created_at, approved_at"
)


def _punch_to_entity(row: dict) -> AttendancePunch:
    return AttendancePunch(
        id=row["id"], employee_id=row["employee_id"], branch_id=row["branch_id"],
        punch_type=PunchType(row["punch_type"]),
        occurred_at=datetime.fromisoformat(row["occurred_at"]),
        source=AttendanceSource(row["source"]), operation_id=row["operation_id"],
        timezone_name=row["timezone_name"], source_reference_id=row["source_reference_id"],
        device_id=row["device_id"], registered_by_user_id=row["registered_by_user_id"],
        notes=row["notes"], created_at=row["created_at"],
    )


def _wd_to_entity(row: dict) -> AttendanceWorkday:
    return AttendanceWorkday(
        id=row["id"], employee_id=row["employee_id"], branch_id=row["branch_id"],
        work_date=date.fromisoformat(row["work_date"]),
        status=WorkdayStatus(row["status"]),
        scheduled_shift_id=row["scheduled_shift_id"],
        first_entry_at=datetime.fromisoformat(row["first_entry_at"]) if row["first_entry_at"] else None,
        last_exit_at=datetime.fromisoformat(row["last_exit_at"]) if row["last_exit_at"] else None,
        worked_minutes=row["worked_minutes"], late_minutes=row["late_minutes"],
        overtime_minutes=row["overtime_minutes"],
        incident_type=AttendanceIncidentType(row["incident_type"]) if row["incident_type"] else None,
        calculation_version=row["calculation_version"],
        created_at=row["created_at"], updated_at=row["updated_at"],
    )


class AttendanceRepository(HRRepositoryBase):
    # ── punches (immutable) ───────────────────────────────────────────────
    def save_punch(self, punch: AttendancePunch, *, workday_id: str | None = None) -> None:
        self._execute(
            f"INSERT INTO attendance_punches ({_PUNCH_COLS})"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (punch.id, punch.employee_id, punch.branch_id, workday_id,
             punch.punch_type.value, punch.occurred_at.isoformat(), punch.timezone_name,
             punch.source.value, punch.source_reference_id, punch.device_id,
             punch.registered_by_user_id, punch.operation_id, punch.notes,
             punch.created_at))

    def find_punch_by_operation_id(self, operation_id: str) -> AttendancePunch | None:
        row = self._query_one(
            f"SELECT {_PUNCH_COLS} FROM attendance_punches WHERE operation_id=?",
            (operation_id,))
        return _punch_to_entity(row) if row else None

    def find_punch_by_source_reference(
        self, source: str, source_reference_id: str, punch_type: str,
    ) -> AttendancePunch | None:
        row = self._query_one(
            f"SELECT {_PUNCH_COLS} FROM attendance_punches"
            " WHERE source=? AND source_reference_id=? AND punch_type=?",
            (source, source_reference_id, punch_type))
        return _punch_to_entity(row) if row else None

    def list_punches_for_workday(self, workday_id: str) -> list[AttendancePunch]:
        rows = self._query(
            f"SELECT {_PUNCH_COLS} FROM attendance_punches WHERE workday_id=?"
            " ORDER BY occurred_at", (workday_id,))
        return [_punch_to_entity(r) for r in rows]

    def attach_punch_to_workday(self, punch_id: str, workday_id: str) -> None:
        self._execute(
            "UPDATE attendance_punches SET workday_id=? WHERE id=?", (workday_id, punch_id))

    # ── workdays ──────────────────────────────────────────────────────────
    def save_workday(self, workday: AttendanceWorkday) -> None:
        self._execute(
            f"INSERT INTO attendance_workdays ({_WD_COLS})"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            self._wd_params(workday))

    def update_workday(self, workday: AttendanceWorkday) -> None:
        self._execute(
            "UPDATE attendance_workdays SET scheduled_shift_id=?, first_entry_at=?,"
            " last_exit_at=?, worked_minutes=?, late_minutes=?, overtime_minutes=?,"
            " status=?, incident_type=?, calculation_version=?, updated_at=? WHERE id=?",
            (workday.scheduled_shift_id,
             workday.first_entry_at.isoformat() if workday.first_entry_at else None,
             workday.last_exit_at.isoformat() if workday.last_exit_at else None,
             workday.worked_minutes, workday.late_minutes, workday.overtime_minutes,
             workday.status.value,
             workday.incident_type.value if workday.incident_type else None,
             workday.calculation_version, workday.updated_at, workday.id))

    def get_workday(self, workday_id: str) -> AttendanceWorkday | None:
        row = self._query_one(
            f"SELECT {_WD_COLS} FROM attendance_workdays WHERE id=?", (workday_id,))
        return _wd_to_entity(row) if row else None

    def find_workday(self, employee_id: str, work_date: date) -> AttendanceWorkday | None:
        row = self._query_one(
            f"SELECT {_WD_COLS} FROM attendance_workdays"
            " WHERE employee_id=? AND work_date=?",
            (employee_id, work_date.isoformat()))
        return _wd_to_entity(row) if row else None

    def list_workdays(self, *, work_date: date | None = None,
                      branch_id: str | None = None) -> list[AttendanceWorkday]:
        conditions, params = ["1=1"], []
        if work_date:
            conditions.append("work_date=?")
            params.append(work_date.isoformat())
        if branch_id:
            conditions.append("branch_id=?")
            params.append(branch_id)
        rows = self._query(
            f"SELECT {_WD_COLS} FROM attendance_workdays"
            f" WHERE {' AND '.join(conditions)} ORDER BY work_date DESC", tuple(params))
        return [_wd_to_entity(r) for r in rows]

    @staticmethod
    def _wd_params(w: AttendanceWorkday) -> tuple:
        return (w.id, w.employee_id, w.branch_id, w.work_date.isoformat(),
                w.scheduled_shift_id,
                w.first_entry_at.isoformat() if w.first_entry_at else None,
                w.last_exit_at.isoformat() if w.last_exit_at else None,
                w.worked_minutes, w.late_minutes, w.overtime_minutes, w.status.value,
                w.incident_type.value if w.incident_type else None,
                w.calculation_version, w.created_at, w.updated_at)


class AttendanceAdjustmentRepository(HRRepositoryBase):
    def save(self, adjustment: AttendanceAdjustment) -> None:
        self._execute(
            f"INSERT INTO attendance_adjustments ({_ADJ_COLS})"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (adjustment.id, adjustment.employee_id, adjustment.workday_id,
             adjustment.original_punch_id, adjustment.field_name,
             adjustment.previous_value, adjustment.requested_value, adjustment.reason,
             adjustment.requested_by_user_id, adjustment.approved_by_user_id,
             adjustment.status.value, adjustment.operation_id, adjustment.created_at,
             adjustment.approved_at))

    def update(self, adjustment: AttendanceAdjustment) -> None:
        self._execute(
            "UPDATE attendance_adjustments SET status=?, approved_by_user_id=?,"
            " approved_at=? WHERE id=?",
            (adjustment.status.value, adjustment.approved_by_user_id,
             adjustment.approved_at, adjustment.id))

    def get(self, adjustment_id: str) -> AttendanceAdjustment | None:
        row = self._query_one(
            f"SELECT {_ADJ_COLS} FROM attendance_adjustments WHERE id=?", (adjustment_id,))
        return self._to_entity(row) if row else None

    def find_by_operation_id(self, operation_id: str) -> AttendanceAdjustment | None:
        row = self._query_one(
            f"SELECT {_ADJ_COLS} FROM attendance_adjustments WHERE operation_id=?",
            (operation_id,))
        return self._to_entity(row) if row else None

    def list_pending(self) -> list[AttendanceAdjustment]:
        rows = self._query(
            f"SELECT {_ADJ_COLS} FROM attendance_adjustments WHERE status='PENDING'"
            " ORDER BY created_at")
        return [self._to_entity(r) for r in rows]

    @staticmethod
    def _to_entity(row: dict) -> AttendanceAdjustment:
        return AttendanceAdjustment(
            id=row["id"], employee_id=row["employee_id"], workday_id=row["workday_id"],
            field_name=row["field_name"], previous_value=row["previous_value"],
            requested_value=row["requested_value"], reason=row["reason"],
            requested_by_user_id=row["requested_by_user_id"],
            operation_id=row["operation_id"], original_punch_id=row["original_punch_id"],
            status=AdjustmentStatus(row["status"]),
            approved_by_user_id=row["approved_by_user_id"],
            approved_at=row["approved_at"], created_at=row["created_at"])
