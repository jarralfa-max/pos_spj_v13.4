"""Read-only query service for HR attendance."""

from __future__ import annotations

from sqlite3 import Connection

from backend.application.dto.attendance_dto import AttendanceWorkdayDTO


class AttendanceQueryService:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def list_workdays(self, *, branch_id: str | None = None, limit: int = 50, offset: int = 0) -> list[AttendanceWorkdayDTO]:
        params: list[object] = []
        where = ""
        if branch_id:
            where = "WHERE w.branch_id = ?"
            params.append(branch_id)
        params.extend([limit, offset])
        rows = self._connection.execute(
            f"""
            SELECT w.id, w.employee_id, w.branch_id, w.work_date, w.first_entry_at, w.last_exit_at,
                   w.worked_minutes, w.late_minutes, w.overtime_minutes, w.status,
                   (
                       SELECT p.source FROM attendance_punches p
                       WHERE p.employee_id = w.employee_id AND p.branch_id = w.branch_id
                         AND date(p.occurred_at) = w.work_date
                       ORDER BY p.occurred_at ASC LIMIT 1
                   ) AS source,
                   (
                       SELECT COUNT(*) FROM attendance_incidents i
                       WHERE i.employee_id = w.employee_id AND i.branch_id = w.branch_id
                         AND i.work_date = w.work_date AND i.status = 'PENDING'
                   ) AS pending_incidents
            FROM attendance_workdays w
            {where}
            ORDER BY w.work_date DESC
            LIMIT ? OFFSET ?
            """,
            params,
        ).fetchall()
        return [
            AttendanceWorkdayDTO(
                id=row[0], employee_id=row[1], branch_id=row[2], work_date=row[3],
                first_entry_at=row[4], last_exit_at=row[5], worked_minutes=row[6],
                late_minutes=row[7], overtime_minutes=row[8], status=row[9],
                source=row[10], pending_incidents=row[11],
            )
            for row in rows
        ]
