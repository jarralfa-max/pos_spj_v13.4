"""SQLite repository for HR work shifts, templates, assignments and rest days."""

from __future__ import annotations

from datetime import date, datetime, time
from sqlite3 import Connection

from backend.domain.hr.entities import RestDay, ShiftAssignment, ShiftTemplate, WorkShift


class SQLiteWorkShiftRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def save(self, shift: WorkShift) -> None:
        self._connection.execute(
            """
            INSERT INTO work_shifts (
                id, name, start_time, end_time, crosses_midnight,
                break_minutes, late_tolerance_minutes, branch_id, active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                start_time = excluded.start_time,
                end_time = excluded.end_time,
                crosses_midnight = excluded.crosses_midnight,
                break_minutes = excluded.break_minutes,
                late_tolerance_minutes = excluded.late_tolerance_minutes,
                branch_id = excluded.branch_id,
                active = excluded.active
            """,
            (
                shift.id,
                shift.name,
                shift.start_time.isoformat(),
                shift.end_time.isoformat(),
                1 if shift.crosses_midnight else 0,
                shift.break_minutes,
                shift.late_tolerance_minutes,
                shift.branch_id,
                1 if shift.active else 0,
            ),
        )

    def get(self, shift_id: str) -> WorkShift | None:
        row = self._connection.execute(
            "SELECT id, name, start_time, end_time, crosses_midnight, break_minutes, late_tolerance_minutes, branch_id, active FROM work_shifts WHERE id = ?",
            (shift_id,),
        ).fetchone()
        return self._row_to_shift(row) if row else None

    def list_active(self, *, branch_id: str | None = None) -> list[WorkShift]:
        params: list[str] = []
        where = "WHERE active = 1"
        if branch_id:
            where += " AND branch_id = ?"
            params.append(branch_id)
        rows = self._connection.execute(
            f"SELECT id, name, start_time, end_time, crosses_midnight, break_minutes, late_tolerance_minutes, branch_id, active FROM work_shifts {where} ORDER BY name",
            tuple(params),
        ).fetchall()
        return [self._row_to_shift(row) for row in rows]

    def assign(self, assignment: ShiftAssignment) -> None:
        self._connection.execute(
            """
            INSERT INTO shift_assignments (
                id, employee_id, work_shift_id, effective_from, effective_to, weekdays, branch_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                employee_id = excluded.employee_id,
                work_shift_id = excluded.work_shift_id,
                effective_from = excluded.effective_from,
                effective_to = excluded.effective_to,
                weekdays = excluded.weekdays,
                branch_id = excluded.branch_id
            """,
            (
                assignment.id,
                assignment.employee_id,
                assignment.work_shift_id,
                assignment.effective_from.isoformat(),
                assignment.effective_to.isoformat() if assignment.effective_to else None,
                assignment.weekdays,
                assignment.branch_id,
            ),
        )

    def list_assignments(self, *, employee_id: str | None = None, branch_id: str | None = None) -> list[ShiftAssignment]:
        clauses: list[str] = []
        params: list[str] = []
        if employee_id:
            clauses.append("employee_id = ?")
            params.append(employee_id)
        if branch_id:
            clauses.append("branch_id = ?")
            params.append(branch_id)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        rows = self._connection.execute(
            "SELECT id, employee_id, work_shift_id, effective_from, effective_to, weekdays, branch_id FROM shift_assignments"
            + where
            + " ORDER BY effective_from DESC",
            tuple(params),
        ).fetchall()
        return [self._row_to_assignment(row) for row in rows]

    def save_template(self, template: ShiftTemplate) -> None:
        self._connection.execute(
            """
            INSERT INTO shift_templates (id, name, branch_id, weekdays, work_shift_id, active)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                branch_id = excluded.branch_id,
                weekdays = excluded.weekdays,
                work_shift_id = excluded.work_shift_id,
                active = excluded.active
            """,
            (template.id, template.name, template.branch_id, template.weekdays, template.work_shift_id, 1 if template.active else 0),
        )

    def list_templates(self, *, branch_id: str | None = None) -> list[ShiftTemplate]:
        params: list[str] = []
        where = "WHERE active = 1"
        if branch_id:
            where += " AND branch_id = ?"
            params.append(branch_id)
        rows = self._connection.execute(
            f"SELECT id, name, branch_id, weekdays, work_shift_id, active FROM shift_templates {where} ORDER BY name",
            tuple(params),
        ).fetchall()
        return [self._row_to_template(row) for row in rows]

    def save_rest_day(self, rest_day: RestDay) -> None:
        self._connection.execute(
            """
            INSERT INTO rest_days (id, employee_id, branch_id, rest_date, reason, active, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(employee_id, branch_id, rest_date) DO UPDATE SET
                reason = excluded.reason,
                active = excluded.active
            """,
            (
                rest_day.id,
                rest_day.employee_id,
                rest_day.branch_id,
                rest_day.rest_date.isoformat(),
                rest_day.reason,
                1 if rest_day.active else 0,
                rest_day.created_at.isoformat(),
            ),
        )

    def list_rest_days(self, *, employee_id: str | None = None, branch_id: str | None = None) -> list[RestDay]:
        clauses = ["active = 1"]
        params: list[str] = []
        if employee_id:
            clauses.append("employee_id = ?")
            params.append(employee_id)
        if branch_id:
            clauses.append("branch_id = ?")
            params.append(branch_id)
        rows = self._connection.execute(
            "SELECT id, employee_id, branch_id, rest_date, reason, active, created_at FROM rest_days WHERE "
            + " AND ".join(clauses)
            + " ORDER BY rest_date DESC",
            tuple(params),
        ).fetchall()
        return [self._row_to_rest_day(row) for row in rows]

    def _row_to_shift(self, row) -> WorkShift:
        return WorkShift(
            id=row[0],
            name=row[1],
            start_time=time.fromisoformat(row[2]),
            end_time=time.fromisoformat(row[3]),
            crosses_midnight=bool(row[4]),
            break_minutes=row[5],
            late_tolerance_minutes=row[6],
            branch_id=row[7],
            active=bool(row[8]),
        )

    def _row_to_assignment(self, row) -> ShiftAssignment:
        return ShiftAssignment(
            id=row[0],
            employee_id=row[1],
            work_shift_id=row[2],
            effective_from=date.fromisoformat(row[3]),
            effective_to=date.fromisoformat(row[4]) if row[4] else None,
            weekdays=row[5],
            branch_id=row[6],
        )

    def _row_to_template(self, row) -> ShiftTemplate:
        return ShiftTemplate(id=row[0], name=row[1], branch_id=row[2], weekdays=row[3], work_shift_id=row[4], active=bool(row[5]))

    def _row_to_rest_day(self, row) -> RestDay:
        return RestDay(
            id=row[0],
            employee_id=row[1],
            branch_id=row[2],
            rest_date=date.fromisoformat(row[3]),
            reason=row[4],
            active=bool(row[5]),
            created_at=datetime.fromisoformat(row[6]),
        )
