"""Presenter boundary for the canonical HR desktop module."""

from __future__ import annotations

from typing import Protocol

from frontend.desktop.modules.hr.hr_view_models import HRDashboardKpiViewModel, HREmployeeFormOptionsViewModel, HREmployeeFormViewModel, HRAttendanceFormViewModel, HRAttendanceRowViewModel, HREmployeeRowViewModel, HRLeaveRowViewModel, HRPayrollRunRowViewModel, HRShiftRowViewModel


class HRPresenterPort(Protocol):
    """Read/write boundary used by HR views without exposing DB or repositories."""

    def load_dashboard(self) -> HRDashboardKpiViewModel:
        """Return dashboard KPI values from HRDashboardQueryService."""

    def list_employees(self, *, search_text: str = "", limit: int = 50, offset: int = 0) -> list[HREmployeeRowViewModel]:
        """Return employee rows from an employee QueryService."""


    def list_attendance(self, *, branch_id: str | None = None, limit: int = 50, offset: int = 0) -> list[HRAttendanceRowViewModel]:
        """Return attendance rows from AttendanceQueryService."""

    def submit_manual_attendance(self, form: HRAttendanceFormViewModel) -> None:
        """Submit manual attendance through a canonical UseCase."""

    def load_employee_form_options(self) -> HREmployeeFormOptionsViewModel:
        """Return configurable catalog options used by the employee form."""

    def submit_create_employee(self, form: HREmployeeFormViewModel) -> None:
        """Submit an employee creation form through a canonical UseCase."""

    def request_create_employee(self) -> None:
        """Open/create flow handled by application UseCases outside the widget."""

    def load_employee_form(self, employee_id: str) -> HREmployeeFormViewModel | None:
        """Return current employee data for update dialogs."""

    def submit_update_employee(self, employee_id: str, form: HREmployeeFormViewModel) -> None:
        """Submit an employee update form through a canonical UseCase."""

    def request_update_employee(self, employee_id: str) -> None:
        """Open/update flow handled by application UseCases outside the widget."""

    def submit_deactivate_employee(self, employee_id: str, reason: str) -> None:
        """Submit employee deactivation through a canonical UseCase."""

    def request_deactivate_employee(self, employee_id: str) -> None:
        """Deactivate flow handled by application UseCases outside the widget."""


    def list_shifts(self, *, branch_id: str | None = None, limit: int = 50, offset: int = 0) -> list[HRLeaveRowViewModel, HRPayrollRunRowViewModel, HRShiftRowViewModel]:
        """Return work shifts from ShiftQueryService."""


    def list_leave_requests(self, *, branch_id: str | None = None, status: str | None = None, limit: int = 50, offset: int = 0) -> list[HRLeaveRowViewModel]:
        """Return leave requests from LeaveQueryService."""


    def list_payroll_runs(self, *, branch_id: str | None = None, limit: int = 50, offset: int = 0) -> list[HRPayrollRunRowViewModel]:
        """Return payroll runs from PayrollQueryService."""
