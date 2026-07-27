"""Read-only query service for HR dashboard KPIs."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from sqlite3 import Connection

from backend.application.dto.hr_dashboard_dto import HRDashboardDTO


class HRDashboardQueryService:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def get_dashboard(self, *, today: date | None = None) -> HRDashboardDTO:
        work_date = (today or date.today()).isoformat()
        active_employees = self._scalar("SELECT COUNT(*) FROM employees WHERE active = 1")
        present_staff = self._scalar(
            "SELECT COUNT(*) FROM attendance_workdays WHERE work_date = ? AND first_entry_at IS NOT NULL",
            (work_date,),
        )
        today_absences = self._scalar(
            "SELECT COUNT(*) FROM attendance_workdays WHERE work_date = ? AND status = 'ABSENT'",
            (work_date,),
        )
        late_arrivals = self._scalar(
            "SELECT COUNT(*) FROM attendance_workdays WHERE work_date = ? AND late_minutes > 0",
            (work_date,),
        )
        pending_requests = self._scalar("SELECT COUNT(*) FROM leave_requests WHERE status = 'PENDING'")
        overtime_minutes = self._scalar(
            "SELECT COALESCE(SUM(overtime_minutes), 0) FROM attendance_workdays WHERE work_date = ?",
            (work_date,),
        )
        estimated_payroll_cost = Decimal(str(self._scalar("SELECT COALESCE(SUM(daily_salary), 0) FROM employees WHERE active = 1")))
        pending_incidents = self._scalar("SELECT COUNT(*) FROM attendance_incidents WHERE status = 'PENDING'")
        return HRDashboardDTO(
            active_employees=active_employees,
            present_staff=present_staff,
            today_absences=today_absences,
            late_arrivals=late_arrivals,
            pending_requests=pending_requests,
            overtime_minutes=overtime_minutes,
            estimated_payroll_cost=estimated_payroll_cost,
            pending_incidents=pending_incidents,
        )

    def _scalar(self, sql: str, params: tuple[object, ...] = ()) -> int | float:
        row = self._connection.execute(sql, params).fetchone()
        return row[0] if row and row[0] is not None else 0
