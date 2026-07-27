"""SQLite repository for immutable attendance punches and calculated workdays."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from sqlite3 import Connection, IntegrityError

from backend.domain.hr.entities import AttendanceIncident, AttendancePunch, AttendanceWorkday
from backend.domain.hr.enums import (
    AttendanceIncidentStatus,
    AttendanceIncidentType,
    AttendanceSource,
    PunchType,
    WorkdayStatus,
)


def _parse_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _punch_from_row(row) -> AttendancePunch:
    return AttendancePunch(
        id=row[0],
        employee_id=row[1],
        branch_id=row[2],
        punch_type=PunchType(row[3]),
        occurred_at=datetime.fromisoformat(row[4]),
        timezone=row[5],
        source=AttendanceSource(row[6]),
        source_reference_id=row[7],
        device_id=row[8],
        registered_by_user_id=row[9],
        operation_id=row[10],
        notes=row[11],
        created_at=datetime.fromisoformat(row[12]),
    )


def _workday_from_row(row) -> AttendanceWorkday:
    return AttendanceWorkday(
        id=row[0],
        employee_id=row[1],
        branch_id=row[2],
        work_date=date.fromisoformat(row[3]),
        scheduled_shift_id=row[4],
        first_entry_at=_parse_datetime(row[5]),
        last_exit_at=_parse_datetime(row[6]),
        worked_minutes=row[7],
        late_minutes=row[8],
        overtime_minutes=row[9],
        status=WorkdayStatus(row[10]),
        calculation_version=row[11],
        created_at=datetime.fromisoformat(row[12]),
        updated_at=datetime.fromisoformat(row[13]),
    )


def _incident_from_row(row) -> AttendanceIncident:
    return AttendanceIncident(
        id=row[0],
        employee_id=row[1],
        branch_id=row[2],
        work_date=date.fromisoformat(row[3]),
        incident_type=AttendanceIncidentType(row[4]),
        status=AttendanceIncidentStatus(row[5]),
        source_reference_id=row[6],
        operation_id=row[7],
        notes=row[8],
        created_at=datetime.fromisoformat(row[9]),
        resolved_at=_parse_datetime(row[10]),
    )


class SQLiteAttendanceRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def add_punch(self, punch: AttendancePunch) -> None:
        self._connection.execute(
            """
            INSERT INTO attendance_punches (
                id, employee_id, branch_id, punch_type, occurred_at, timezone,
                source, source_reference_id, device_id, registered_by_user_id,
                operation_id, notes, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                punch.id,
                punch.employee_id,
                punch.branch_id,
                punch.punch_type.value,
                punch.occurred_at.isoformat(),
                punch.timezone,
                punch.source.value,
                punch.source_reference_id,
                punch.device_id,
                punch.registered_by_user_id,
                punch.operation_id,
                punch.notes,
                punch.created_at.isoformat(),
            ),
        )

    def get_punch(self, punch_id: str) -> AttendancePunch | None:
        row = self._connection.execute(
            """
            SELECT id, employee_id, branch_id, punch_type, occurred_at, timezone,
                   source, source_reference_id, device_id, registered_by_user_id,
                   operation_id, notes, created_at
            FROM attendance_punches WHERE id = ?
            """,
            (punch_id,),
        ).fetchone()
        return _punch_from_row(row) if row else None

    def get_punch_by_operation_id(self, operation_id: str) -> AttendancePunch | None:
        row = self._connection.execute(
            """
            SELECT id, employee_id, branch_id, punch_type, occurred_at, timezone,
                   source, source_reference_id, device_id, registered_by_user_id,
                   operation_id, notes, created_at
            FROM attendance_punches WHERE operation_id = ?
            """,
            (operation_id,),
        ).fetchone()
        return _punch_from_row(row) if row else None

    def get_punch_by_source_reference(self, source: str, source_reference_id: str, punch_type: str) -> AttendancePunch | None:
        row = self._connection.execute(
            """
            SELECT id, employee_id, branch_id, punch_type, occurred_at, timezone,
                   source, source_reference_id, device_id, registered_by_user_id,
                   operation_id, notes, created_at
            FROM attendance_punches
            WHERE source = ? AND source_reference_id = ? AND punch_type = ?
            """,
            (source, source_reference_id, punch_type),
        ).fetchone()
        return _punch_from_row(row) if row else None

    def list_punches_for_workday(self, *, employee_id: str, branch_id: str, work_date: date) -> list[AttendancePunch]:
        start_at = datetime.combine(work_date, time.min)
        end_at = start_at + timedelta(days=1)
        rows = self._connection.execute(
            """
            SELECT id, employee_id, branch_id, punch_type, occurred_at, timezone,
                   source, source_reference_id, device_id, registered_by_user_id,
                   operation_id, notes, created_at
            FROM attendance_punches
            WHERE employee_id = ? AND branch_id = ? AND occurred_at >= ? AND occurred_at < ?
            ORDER BY occurred_at ASC, created_at ASC
            """,
            (employee_id, branch_id, start_at.isoformat(), end_at.isoformat()),
        ).fetchall()
        return [_punch_from_row(row) for row in rows]

    def save_workday(self, workday: AttendanceWorkday) -> None:
        self._connection.execute(
            """
            INSERT INTO attendance_workdays (
                id, employee_id, branch_id, work_date, scheduled_shift_id,
                first_entry_at, last_exit_at, worked_minutes, late_minutes,
                overtime_minutes, status, calculation_version, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(employee_id, branch_id, work_date) DO UPDATE SET
                scheduled_shift_id = excluded.scheduled_shift_id,
                first_entry_at = excluded.first_entry_at,
                last_exit_at = excluded.last_exit_at,
                worked_minutes = excluded.worked_minutes,
                late_minutes = excluded.late_minutes,
                overtime_minutes = excluded.overtime_minutes,
                status = excluded.status,
                calculation_version = excluded.calculation_version,
                updated_at = excluded.updated_at
            """,
            (
                workday.id,
                workday.employee_id,
                workday.branch_id,
                workday.work_date.isoformat(),
                workday.scheduled_shift_id,
                workday.first_entry_at.isoformat() if workday.first_entry_at else None,
                workday.last_exit_at.isoformat() if workday.last_exit_at else None,
                workday.worked_minutes,
                workday.late_minutes,
                workday.overtime_minutes,
                workday.status.value,
                workday.calculation_version,
                workday.created_at.isoformat(),
                workday.updated_at.isoformat(),
            ),
        )

    def get_workday(self, *, employee_id: str, branch_id: str, work_date: date) -> AttendanceWorkday | None:
        row = self._connection.execute(
            """
            SELECT id, employee_id, branch_id, work_date, scheduled_shift_id,
                   first_entry_at, last_exit_at, worked_minutes, late_minutes,
                   overtime_minutes, status, calculation_version, created_at, updated_at
            FROM attendance_workdays
            WHERE employee_id = ? AND branch_id = ? AND work_date = ?
            """,
            (employee_id, branch_id, work_date.isoformat()),
        ).fetchone()
        return _workday_from_row(row) if row else None

    def add_incident(self, incident: AttendanceIncident) -> None:
        try:
            self._connection.execute(
                """
                INSERT INTO attendance_incidents (
                    id, employee_id, branch_id, work_date, incident_type, status,
                    source_reference_id, operation_id, notes, created_at, resolved_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    incident.id,
                    incident.employee_id,
                    incident.branch_id,
                    incident.work_date.isoformat(),
                    incident.incident_type.value,
                    incident.status.value,
                    incident.source_reference_id,
                    incident.operation_id,
                    incident.notes,
                    incident.created_at.isoformat(),
                    incident.resolved_at.isoformat() if incident.resolved_at else None,
                ),
            )
        except IntegrityError as exc:
            if "attendance_incidents.operation_id" not in str(exc):
                raise

    def list_incidents(self, *, employee_id: str, branch_id: str, work_date: date) -> list[AttendanceIncident]:
        rows = self._connection.execute(
            """
            SELECT id, employee_id, branch_id, work_date, incident_type, status,
                   source_reference_id, operation_id, notes, created_at, resolved_at
            FROM attendance_incidents
            WHERE employee_id = ? AND branch_id = ? AND work_date = ?
            ORDER BY created_at ASC
            """,
            (employee_id, branch_id, work_date.isoformat()),
        ).fetchall()
        return [_incident_from_row(row) for row in rows]
