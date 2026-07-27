"""Canonical HR entities using UUIDv7 string identities."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from decimal import Decimal

from backend.shared.ids import new_uuid

from .enums import (
    AdjustmentStatus,
    AttendanceIncidentStatus,
    AttendanceIncidentType,
    AttendanceSource,
    ContractType,
    EmploymentStatus,
    LeaveStatus,
    LeaveType,
    PaymentFrequency,
    PayrollConceptCode,
    PayrollRunStatus,
    PunchType,
    WorkdayStatus,
)


def _id() -> str:
    return new_uuid()


@dataclass(slots=True)
class Employee:
    employee_code: str
    first_name: str
    last_name: str
    branch_id: str
    department_id: str
    position_id: str
    contract_type: ContractType
    payment_frequency: PaymentFrequency
    base_salary: Decimal
    daily_salary: Decimal
    hire_date: date
    id: str = field(default_factory=_id)
    phone_e164: str | None = None
    email: str | None = None
    supervisor_employee_id: str | None = None
    employment_status: EmploymentStatus = EmploymentStatus.ACTIVE
    termination_date: date | None = None
    termination_reason: str | None = None
    bank_account_reference: str | None = None
    tax_identifier: str | None = None
    emergency_contact_name: str | None = None
    emergency_contact_phone: str | None = None
    active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(slots=True)
class Department:
    name: str
    branch_id: str
    id: str = field(default_factory=_id)
    active: bool = True


@dataclass(slots=True)
class Position:
    name: str
    department_id: str
    id: str = field(default_factory=_id)
    active: bool = True


@dataclass(slots=True)
class ContractTypeCatalogItem:
    code: str
    name: str
    id: str = field(default_factory=_id)
    active: bool = True


@dataclass(slots=True)
class PaymentFrequencyCatalogItem:
    code: str
    name: str
    id: str = field(default_factory=_id)
    active: bool = True


@dataclass(slots=True)
class AttendancePunch:
    employee_id: str
    branch_id: str
    punch_type: PunchType
    occurred_at: datetime
    timezone: str
    source: AttendanceSource
    operation_id: str
    id: str = field(default_factory=_id)
    source_reference_id: str | None = None
    device_id: str | None = None
    registered_by_user_id: str | None = None
    notes: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(slots=True)
class AttendanceWorkday:
    employee_id: str
    branch_id: str
    work_date: date
    status: WorkdayStatus
    id: str = field(default_factory=_id)
    scheduled_shift_id: str | None = None
    first_entry_at: datetime | None = None
    last_exit_at: datetime | None = None
    worked_minutes: int = 0
    late_minutes: int = 0
    overtime_minutes: int = 0
    calculation_version: str = "HR_V1"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(slots=True)
class AttendanceIncident:
    employee_id: str
    branch_id: str
    work_date: date
    incident_type: AttendanceIncidentType
    operation_id: str
    id: str = field(default_factory=_id)
    status: AttendanceIncidentStatus = AttendanceIncidentStatus.PENDING
    source_reference_id: str | None = None
    notes: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    resolved_at: datetime | None = None


@dataclass(slots=True)
class AttendanceAdjustment:
    original_punch_id: str
    requested_value: datetime
    previous_value: datetime
    reason: str
    requested_by_user_id: str
    id: str = field(default_factory=_id)
    approved_by_user_id: str | None = None
    status: AdjustmentStatus = AdjustmentStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    approved_at: datetime | None = None


@dataclass(slots=True)
class WorkShift:
    name: str
    start_time: time
    end_time: time
    crosses_midnight: bool
    break_minutes: int
    late_tolerance_minutes: int
    branch_id: str
    id: str = field(default_factory=_id)
    active: bool = True


@dataclass(slots=True)
class ShiftAssignment:
    employee_id: str
    work_shift_id: str
    effective_from: date
    weekdays: str
    branch_id: str
    id: str = field(default_factory=_id)
    effective_to: date | None = None


@dataclass(slots=True)
class ShiftTemplate:
    name: str
    branch_id: str
    weekdays: str
    work_shift_id: str
    id: str = field(default_factory=_id)
    active: bool = True


@dataclass(slots=True)
class RestDay:
    employee_id: str
    branch_id: str
    rest_date: date
    reason: str
    id: str = field(default_factory=_id)
    active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(slots=True)
class LeaveRequest:
    employee_id: str
    branch_id: str
    leave_type: LeaveType
    start_date: date
    end_date: date
    requested_days: Decimal
    reason: str
    requested_by_user_id: str
    operation_id: str
    id: str = field(default_factory=_id)
    status: LeaveStatus = LeaveStatus.DRAFT
    approved_by_user_id: str | None = None
    approved_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(slots=True)
class PayrollRun:
    branch_id: str
    period_start: date
    period_end: date
    operation_id: str
    id: str = field(default_factory=_id)
    status: PayrollRunStatus = PayrollRunStatus.DRAFT
    gross_amount: Decimal = Decimal("0")
    deductions_amount: Decimal = Decimal("0")
    net_amount: Decimal = Decimal("0")
    authorized_by_user_id: str | None = None
    paid_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(slots=True)
class PayrollLine:
    payroll_run_id: str
    employee_id: str
    gross_amount: Decimal
    deductions_amount: Decimal
    net_amount: Decimal
    id: str = field(default_factory=_id)


@dataclass(slots=True)
class PayrollConcept:
    payroll_line_id: str
    concept_code: PayrollConceptCode
    amount: Decimal
    id: str = field(default_factory=_id)
    notes: str | None = None


@dataclass(slots=True)
class PayrollPayment:
    payroll_run_id: str
    branch_id: str
    payment_method: str
    net_amount: Decimal
    operation_id: str
    paid_by_user_id: str
    id: str = field(default_factory=_id)
    paid_at: datetime = field(default_factory=lambda: datetime.now(UTC))
