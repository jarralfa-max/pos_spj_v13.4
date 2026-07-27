"""Read-only QueryService for canonical HR schedules."""

from __future__ import annotations

from sqlite3 import Connection

from backend.application.dto.shift_dto import RestDayDTO, ShiftAssignmentDTO, ShiftTemplateDTO, WorkShiftDTO


class ShiftQueryService:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def list_shifts(self, *, branch_id: str | None = None, limit: int = 50, offset: int = 0) -> list[WorkShiftDTO]:
        params: list[object] = []
        where = "WHERE active = 1"
        if branch_id:
            where += " AND branch_id = ?"
            params.append(branch_id)
        params.extend([limit, offset])
        rows = self._connection.execute(
            f"SELECT id, name, start_time, end_time, crosses_midnight, break_minutes, late_tolerance_minutes, branch_id FROM work_shifts {where} ORDER BY name LIMIT ? OFFSET ?",
            tuple(params),
        ).fetchall()
        return [WorkShiftDTO(id=r[0], name=r[1], start_time=r[2], end_time=r[3], crosses_midnight=bool(r[4]), break_minutes=int(r[5]), late_tolerance_minutes=int(r[6]), branch_id=r[7]) for r in rows]

    def list_assignments(self, *, branch_id: str | None = None, employee_id: str | None = None, limit: int = 50, offset: int = 0) -> list[ShiftAssignmentDTO]:
        clauses: list[str] = []
        params: list[object] = []
        if branch_id:
            clauses.append("branch_id = ?")
            params.append(branch_id)
        if employee_id:
            clauses.append("employee_id = ?")
            params.append(employee_id)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        params.extend([limit, offset])
        rows = self._connection.execute(
            "SELECT id, employee_id, work_shift_id, effective_from, effective_to, weekdays, branch_id FROM shift_assignments"
            + where
            + " ORDER BY effective_from DESC LIMIT ? OFFSET ?",
            tuple(params),
        ).fetchall()
        return [ShiftAssignmentDTO(id=r[0], employee_id=r[1], work_shift_id=r[2], effective_from=r[3], effective_to=r[4], weekdays=r[5], branch_id=r[6]) for r in rows]

    def list_templates(self, *, branch_id: str | None = None) -> list[ShiftTemplateDTO]:
        params: list[object] = []
        where = "WHERE active = 1"
        if branch_id:
            where += " AND branch_id = ?"
            params.append(branch_id)
        rows = self._connection.execute(
            f"SELECT id, name, branch_id, weekdays, work_shift_id FROM shift_templates {where} ORDER BY name",
            tuple(params),
        ).fetchall()
        return [ShiftTemplateDTO(id=r[0], name=r[1], branch_id=r[2], weekdays=r[3], work_shift_id=r[4]) for r in rows]

    def list_rest_days(self, *, branch_id: str | None = None, employee_id: str | None = None) -> list[RestDayDTO]:
        clauses = ["active = 1"]
        params: list[object] = []
        if branch_id:
            clauses.append("branch_id = ?")
            params.append(branch_id)
        if employee_id:
            clauses.append("employee_id = ?")
            params.append(employee_id)
        rows = self._connection.execute(
            "SELECT id, employee_id, branch_id, rest_date, reason FROM rest_days WHERE "
            + " AND ".join(clauses)
            + " ORDER BY rest_date DESC",
            tuple(params),
        ).fetchall()
        return [RestDayDTO(id=r[0], employee_id=r[1], branch_id=r[2], rest_date=r[3], reason=r[4]) for r in rows]
