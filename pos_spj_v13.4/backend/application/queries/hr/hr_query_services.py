"""Read-only query services for the HR bounded context (UI + BI feed).

No mutations, no commit. Return display-ready dict rows with paging/filters.
"""

from __future__ import annotations

from typing import Any


class _HRQueryBase:
    def __init__(self, connection: Any) -> None:
        self._conn = connection

    def _query(self, sql: str, params: tuple = ()) -> list[dict]:
        cursor = self._conn.execute(sql, params)
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def _scalar(self, sql: str, params: tuple = (), default: Any = 0) -> Any:
        row = self._conn.execute(sql, params).fetchone()
        return row[0] if row and row[0] is not None else default


class EmployeeQueryService(_HRQueryBase):
    def list_employees(self, *, branch_id: str | None = None, active_only: bool = True,
                       search: str | None = None, limit: int = 100, offset: int = 0) -> list[dict]:
        conditions, params = ["1=1"], []
        if active_only:
            conditions.append("e.active=1")
        if branch_id:
            conditions.append("e.branch_id=?")
            params.append(branch_id)
        if search:
            conditions.append("(e.first_name LIKE ? OR e.last_name LIKE ? OR e.employee_code LIKE ?)")
            like = f"%{search}%"
            params.extend([like, like, like])
        params.extend([limit, offset])
        return self._query(
            "SELECT e.id, e.employee_code, e.first_name, e.last_name, e.branch_id,"
            " e.employment_status, e.hire_date, e.active,"
            " d.name AS department_name, p.name AS position_name"
            " FROM employees e"
            " LEFT JOIN hr_departments d ON d.id=e.department_id"
            " LEFT JOIN hr_positions p ON p.id=e.position_id"
            f" WHERE {' AND '.join(conditions)}"
            " ORDER BY e.last_name, e.first_name LIMIT ? OFFSET ?", tuple(params))

    def get_employee(self, employee_id: str) -> dict | None:
        rows = self._query(
            "SELECT e.*, d.name AS department_name, p.name AS position_name"
            " FROM employees e"
            " LEFT JOIN hr_departments d ON d.id=e.department_id"
            " LEFT JOIN hr_positions p ON p.id=e.position_id WHERE e.id=?", (employee_id,))
        return rows[0] if rows else None


class AttendanceQueryService(_HRQueryBase):
    def list_workdays(self, *, work_date: str | None = None, branch_id: str | None = None,
                      limit: int = 200) -> list[dict]:
        conditions, params = ["1=1"], []
        if work_date:
            conditions.append("w.work_date=?")
            params.append(work_date)
        if branch_id:
            conditions.append("w.branch_id=?")
            params.append(branch_id)
        params.append(limit)
        return self._query(
            "SELECT w.id, w.employee_id, e.first_name || ' ' || e.last_name AS employee_name,"
            " w.branch_id, w.work_date, w.first_entry_at, w.last_exit_at, w.worked_minutes,"
            " w.late_minutes, w.overtime_minutes, w.status, w.incident_type"
            " FROM attendance_workdays w JOIN employees e ON e.id=w.employee_id"
            f" WHERE {' AND '.join(conditions)}"
            " ORDER BY w.work_date DESC, employee_name LIMIT ?", tuple(params))

    def workday_punches(self, workday_id: str) -> list[dict]:
        return self._query(
            "SELECT punch_type, occurred_at, source, registered_by_user_id, notes"
            " FROM attendance_punches WHERE workday_id=? ORDER BY occurred_at", (workday_id,))

    def pending_adjustments(self) -> list[dict]:
        return self._query(
            "SELECT a.id, a.employee_id, e.first_name || ' ' || e.last_name AS employee_name,"
            " a.field_name, a.previous_value, a.requested_value, a.reason, a.status"
            " FROM attendance_adjustments a JOIN employees e ON e.id=a.employee_id"
            " WHERE a.status='PENDING' ORDER BY a.created_at")


class LeaveQueryService(_HRQueryBase):
    def list_requests(self, *, status: str | None = None, employee_id: str | None = None) -> list[dict]:
        conditions, params = ["1=1"], []
        if status:
            conditions.append("l.status=?")
            params.append(status)
        if employee_id:
            conditions.append("l.employee_id=?")
            params.append(employee_id)
        return self._query(
            "SELECT l.id, l.employee_id, e.first_name || ' ' || e.last_name AS employee_name,"
            " l.leave_type, l.start_date, l.end_date, l.requested_days, l.status, l.reason"
            " FROM leave_requests l JOIN employees e ON e.id=l.employee_id"
            f" WHERE {' AND '.join(conditions)} ORDER BY l.start_date DESC", tuple(params))


class PayrollQueryService(_HRQueryBase):
    def list_runs(self, *, status: str | None = None) -> list[dict]:
        if status:
            return self._query(
                "SELECT id, period_start, period_end, branch_id, status,"
                " authorized_by_user_id, paid_at FROM payroll_runs WHERE status=?"
                " ORDER BY period_start DESC", (status,))
        return self._query(
            "SELECT id, period_start, period_end, branch_id, status,"
            " authorized_by_user_id, paid_at FROM payroll_runs"
            " ORDER BY period_start DESC LIMIT 200")

    def run_lines(self, payroll_run_id: str) -> list[dict]:
        return self._query(
            "SELECT pl.employee_id, e.first_name || ' ' || e.last_name AS employee_name,"
            " pl.concept, pl.amount, pl.is_deduction, pl.quantity"
            " FROM payroll_lines pl JOIN employees e ON e.id=pl.employee_id"
            " WHERE pl.payroll_run_id=? ORDER BY employee_name, pl.concept",
            (payroll_run_id,))

    def run_totals(self, payroll_run_id: str) -> dict:
        gross = self._scalar(
            "SELECT COALESCE(SUM(CAST(amount AS NUMERIC)),0) FROM payroll_lines"
            " WHERE payroll_run_id=? AND is_deduction=0", (payroll_run_id,))
        deductions = self._scalar(
            "SELECT COALESCE(SUM(CAST(amount AS NUMERIC)),0) FROM payroll_lines"
            " WHERE payroll_run_id=? AND is_deduction=1", (payroll_run_id,))
        return {"gross": str(gross), "deductions": str(deductions),
                "net": str(float(gross) - float(deductions))}


class HRDashboardQueryService(_HRQueryBase):
    def overview(self, *, work_date: str, branch_id: str | None = None) -> dict:
        branch_clause = " AND branch_id=?" if branch_id else ""
        branch_params: tuple = (branch_id,) if branch_id else ()

        active = self._scalar(
            f"SELECT COUNT(*) FROM employees WHERE active=1{branch_clause}", branch_params)
        present = self._scalar(
            "SELECT COUNT(*) FROM attendance_workdays WHERE work_date=? AND status='COMPLETE'"
            + (" AND branch_id=?" if branch_id else ""),
            (work_date, *branch_params))
        late = self._scalar(
            "SELECT COUNT(*) FROM attendance_workdays WHERE work_date=? AND late_minutes>0"
            + (" AND branch_id=?" if branch_id else ""),
            (work_date, *branch_params))
        incidents = self._scalar(
            "SELECT COUNT(*) FROM attendance_workdays WHERE status='INCIDENT'"
            + (" AND branch_id=?" if branch_id else ""),
            branch_params)
        pending_leaves = self._scalar(
            "SELECT COUNT(*) FROM leave_requests WHERE status='PENDING'")
        overtime = self._scalar(
            "SELECT COALESCE(SUM(overtime_minutes),0) FROM attendance_workdays"
            " WHERE work_date=?", (work_date,))
        return {
            "active_employees": active,
            "present_today": present,
            "absences_today": max(0, active - present),
            "late_today": late,
            "pending_requests": pending_leaves,
            "overtime_minutes": overtime,
            "pending_incidents": incidents,
        }
