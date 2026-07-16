"""View models consumed by the canonical HR desktop UI."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class HREmployeeRowViewModel:
    employee_id: str
    employee_code: str
    full_name: str
    branch_name: str
    department_name: str
    position_name: str
    status: str
    hire_date: date | None


@dataclass(frozen=True, slots=True)
class HRDashboardKpiViewModel:
    active_employees: int = 0
    present_staff: int = 0
    absences_today: int = 0
    late_arrivals: int = 0
    pending_requests: int = 0
    overtime_hours: Decimal = Decimal("0")
    estimated_payroll_cost: Decimal = Decimal("0")
    pending_incidents: int = 0

@dataclass(frozen=True, slots=True)
class HRCatalogOptionViewModel:
    id: str
    label: str


@dataclass(frozen=True, slots=True)
class HREmployeeFormOptionsViewModel:
    departments: tuple[HRCatalogOptionViewModel, ...] = ()
    positions: tuple[HRCatalogOptionViewModel, ...] = ()
    contract_types: tuple[HRCatalogOptionViewModel, ...] = ()
    payment_frequencies: tuple[HRCatalogOptionViewModel, ...] = ()


@dataclass(frozen=True, slots=True)
class HREmployeeFormViewModel:
    employee_code: str
    first_name: str
    last_name: str
    branch_id: str
    department_id: str
    position_id: str
    contract_type: str
    payment_frequency: str
    base_salary: Decimal
    daily_salary: Decimal
    hire_date: date
    phone_e164: str | None = None
    email: str | None = None


@dataclass(frozen=True, slots=True)
class HRAttendanceRowViewModel:
    workday_id: str
    employee_label: str
    branch_label: str
    entry_at: str
    exit_at: str
    source_label: str
    worked_hours: Decimal
    status: str
    pending_incidents: int


@dataclass(frozen=True, slots=True)
class HRAttendanceFormViewModel:
    employee_id: str
    branch_id: str
    occurred_at: str
    punch_type: str
    reason: str
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class HRShiftRowViewModel:
    shift_id: str
    name: str
    branch_label: str
    schedule: str
    break_minutes: int
    late_tolerance_minutes: int
    active: bool = True


@dataclass(frozen=True, slots=True)
class HRLeaveRowViewModel:
    leave_request_id: str
    employee_label: str
    branch_label: str
    leave_type: str
    period: str
    requested_days: Decimal
    reason: str
    status: str


@dataclass(frozen=True, slots=True)
class HRPayrollRunRowViewModel:
    payroll_run_id: str
    branch_label: str
    period: str
    status: str
    gross_amount: Decimal
    deductions_amount: Decimal
    net_amount: Decimal
