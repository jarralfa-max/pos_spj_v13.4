"""Presenter implementation for the canonical HR desktop module."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import Protocol

from frontend.desktop.modules.hr.hr_view_models import (
    HRAttendanceFormViewModel,
    HRAttendanceRowViewModel,
    HRCatalogOptionViewModel,
    HRDashboardKpiViewModel,
    HREmployeeFormOptionsViewModel,
    HREmployeeFormViewModel,
    HREmployeeRowViewModel,
    HRLeaveRowViewModel,
    HRPayrollRunRowViewModel,
    HRShiftRowViewModel,
)


class _EmployeeQueryService(Protocol):
    def list_employees(self, *, search: str | None = None, limit: int = 50, offset: int = 0):
        """Return employee DTOs from the application QueryService."""

    def get_employee(self, employee_id: str):
        """Return one employee DTO from the application QueryService."""


class _DashboardQueryService(Protocol):
    def get_dashboard(self):
        """Return dashboard DTO from the application QueryService."""


class _AttendanceQueryService(Protocol):
    def list_workdays(self, *, branch_id: str | None = None, limit: int = 50, offset: int = 0):
        """Return attendance DTOs from the application QueryService."""


class _LeaveQueryService(Protocol):
    def list_requests(self, *, branch_id: str | None = None, status: str | None = None, limit: int = 50, offset: int = 0):
        """Return leave DTOs from the application QueryService."""


class _PayrollQueryService(Protocol):
    def list_runs(self, *, branch_id: str | None = None, limit: int = 50, offset: int = 0):
        """Return payroll DTOs from the application QueryService."""


class _ShiftQueryService(Protocol):
    def list_shifts(self, *, branch_id: str | None = None, limit: int = 50, offset: int = 0):
        """Return shift DTOs from the application QueryService."""


class HRDesktopPresenter:
    """Maps application QueryService DTOs into UI view models."""

    def __init__(
        self,
        *,
        employee_query_service: _EmployeeQueryService,
        dashboard_query_service: _DashboardQueryService,
        catalog_query_service=None,
        attendance_query_service: _AttendanceQueryService | None = None,
        shift_query_service: _ShiftQueryService | None = None,
        leave_query_service: _LeaveQueryService | None = None,
        payroll_query_service: _PayrollQueryService | None = None,
        on_manual_attendance: Callable[[HRAttendanceFormViewModel], None] | None = None,
        on_create_employee: Callable[[HREmployeeFormViewModel], None] | None = None,
        on_update_employee: Callable[[str, HREmployeeFormViewModel], None] | None = None,
        on_deactivate_employee: Callable[[str, str], None] | None = None,
    ) -> None:
        self._employee_query_service = employee_query_service
        self._dashboard_query_service = dashboard_query_service
        self._catalog_query_service = catalog_query_service
        self._attendance_query_service = attendance_query_service
        self._shift_query_service = shift_query_service
        self._leave_query_service = leave_query_service
        self._payroll_query_service = payroll_query_service
        self._on_manual_attendance = on_manual_attendance
        self._on_create_employee = on_create_employee
        self._on_update_employee = on_update_employee
        self._on_deactivate_employee = on_deactivate_employee

    def load_dashboard(self) -> HRDashboardKpiViewModel:
        dto = self._dashboard_query_service.get_dashboard()
        return HRDashboardKpiViewModel(
            active_employees=dto.active_employees,
            present_staff=dto.present_staff,
            absences_today=dto.today_absences,
            late_arrivals=dto.late_arrivals,
            pending_requests=dto.pending_requests,
            overtime_hours=dto.overtime_minutes / 60,
            estimated_payroll_cost=dto.estimated_payroll_cost,
            pending_incidents=dto.pending_incidents,
        )

    def list_employees(self, *, search_text: str = "", limit: int = 50, offset: int = 0) -> list[HREmployeeRowViewModel]:
        employees = self._employee_query_service.list_employees(search=search_text or None, limit=limit, offset=offset)
        return [
            HREmployeeRowViewModel(
                employee_id=employee.id,
                employee_code=employee.employee_code,
                full_name=employee.full_name,
                branch_name=employee.branch_id,
                department_name=employee.department_id,
                position_name=employee.position_id,
                status=employee.employment_status,
                hire_date=date.fromisoformat(employee.hire_date) if employee.hire_date else None,
            )
            for employee in employees
        ]

    def list_attendance(self, *, branch_id: str | None = None, limit: int = 50, offset: int = 0) -> list[HRAttendanceRowViewModel]:
        if self._attendance_query_service is None:
            return []
        source_labels = {
            "CASH_REGISTER": "Caja",
            "MANUAL": "Manual",
            "TIME_CLOCK": "Reloj checador",
            "MOBILE": "Móvil",
            "SYSTEM": "Sistema",
        }
        rows = self._attendance_query_service.list_workdays(branch_id=branch_id, limit=limit, offset=offset)
        return [
            HRAttendanceRowViewModel(
                workday_id=row.id,
                employee_label=row.employee_id,
                branch_label=row.branch_id,
                entry_at=row.first_entry_at or "—",
                exit_at=row.last_exit_at or "—",
                source_label=source_labels.get(row.source or "", row.source or "—"),
                worked_hours=Decimal(row.worked_minutes) / Decimal(60),
                status=row.status,
                pending_incidents=row.pending_incidents,
            )
            for row in rows
        ]

    def list_shifts(self, *, branch_id: str | None = None, limit: int = 50, offset: int = 0) -> list[HRShiftRowViewModel]:
        if self._shift_query_service is None:
            return []
        rows = self._shift_query_service.list_shifts(branch_id=branch_id, limit=limit, offset=offset)
        return [
            HRShiftRowViewModel(
                shift_id=row.id,
                name=row.name,
                branch_label=row.branch_id,
                schedule=f"{row.start_time}–{row.end_time}",
                break_minutes=row.break_minutes,
                late_tolerance_minutes=row.late_tolerance_minutes,
                active=True,
            )
            for row in rows
        ]

    def list_leave_requests(self, *, branch_id: str | None = None, status: str | None = None, limit: int = 50, offset: int = 0) -> list[HRLeaveRowViewModel]:
        if self._leave_query_service is None:
            return []
        rows = self._leave_query_service.list_requests(branch_id=branch_id, status=status, limit=limit, offset=offset)
        return [
            HRLeaveRowViewModel(
                leave_request_id=row.id,
                employee_label=row.employee_id,
                branch_label=row.branch_id,
                leave_type=row.leave_type,
                period=f"{row.start_date} – {row.end_date}",
                requested_days=row.requested_days,
                reason=row.reason,
                status=row.status,
            )
            for row in rows
        ]

    def list_payroll_runs(self, *, branch_id: str | None = None, limit: int = 50, offset: int = 0) -> list[HRPayrollRunRowViewModel]:
        if self._payroll_query_service is None:
            return []
        rows = self._payroll_query_service.list_runs(branch_id=branch_id, limit=limit, offset=offset)
        return [
            HRPayrollRunRowViewModel(
                payroll_run_id=row.id,
                branch_label=row.branch_id,
                period=f"{row.period_start} – {row.period_end}",
                status=row.status,
                gross_amount=row.gross_amount,
                deductions_amount=row.deductions_amount,
                net_amount=row.net_amount,
            )
            for row in rows
        ]

    def submit_manual_attendance(self, form: HRAttendanceFormViewModel) -> None:
        if self._on_manual_attendance is not None:
            self._on_manual_attendance(form)

    def load_employee_form_options(self) -> HREmployeeFormOptionsViewModel:
        if self._catalog_query_service is None:
            return HREmployeeFormOptionsViewModel()
        departments = tuple(
            HRCatalogOptionViewModel(id=item.id, label=item.name)
            for item in self._catalog_query_service.list_departments()
        )
        positions = tuple(
            HRCatalogOptionViewModel(id=item.id, label=item.name)
            for item in self._catalog_query_service.list_positions()
        )
        contract_types = tuple(
            HRCatalogOptionViewModel(id=item.code, label=item.name)
            for item in self._catalog_query_service.list_contract_types()
        )
        payment_frequencies = tuple(
            HRCatalogOptionViewModel(id=item.code, label=item.name)
            for item in self._catalog_query_service.list_payment_frequencies()
        )
        return HREmployeeFormOptionsViewModel(
            departments=departments,
            positions=positions,
            contract_types=contract_types,
            payment_frequencies=payment_frequencies,
        )

    def submit_create_employee(self, form: HREmployeeFormViewModel) -> None:
        if self._on_create_employee is not None:
            self._on_create_employee(form)

    def request_create_employee(self) -> None:
        return None

    def load_employee_form(self, employee_id: str) -> HREmployeeFormViewModel | None:
        employee = self._employee_query_service.get_employee(employee_id)
        if employee is None:
            return None
        return HREmployeeFormViewModel(
            employee_code=employee.employee_code,
            first_name=employee.first_name,
            last_name=employee.last_name,
            branch_id=employee.branch_id,
            department_id=employee.department_id,
            position_id=employee.position_id,
            contract_type=employee.contract_type,
            payment_frequency=employee.payment_frequency,
            base_salary=Decimal(str(employee.base_salary)),
            daily_salary=Decimal(str(employee.daily_salary)),
            hire_date=date.fromisoformat(employee.hire_date),
        )

    def submit_update_employee(self, employee_id: str, form: HREmployeeFormViewModel) -> None:
        if self._on_update_employee is not None:
            self._on_update_employee(employee_id, form)

    def request_update_employee(self, employee_id: str) -> None:
        return None

    def submit_deactivate_employee(self, employee_id: str, reason: str) -> None:
        if self._on_deactivate_employee is not None:
            self._on_deactivate_employee(employee_id, reason)

    def request_deactivate_employee(self, employee_id: str) -> None:
        return None
