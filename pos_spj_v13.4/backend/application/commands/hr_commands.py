"""Commands for canonical HR employee use cases."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time
from decimal import Decimal

from backend.application.commands.base_command import BaseCommand
from backend.domain.hr.enums import ContractType, LeaveType, PaymentFrequency


@dataclass(frozen=True)
class CreateEmployeeCommand(BaseCommand):
    employee_code: str = ""
    first_name: str = ""
    last_name: str = ""
    department_id: str = ""
    position_id: str = ""
    contract_type: ContractType = ContractType.FULL_TIME
    payment_frequency: PaymentFrequency = PaymentFrequency.WEEKLY
    base_salary: Decimal = Decimal("0")
    daily_salary: Decimal = Decimal("0")
    hire_date: date | None = None
    phone_e164: str | None = None
    email: str | None = None
    supervisor_employee_id: str | None = None
    bank_account_reference: str | None = None
    tax_identifier: str | None = None
    emergency_contact_name: str | None = None
    emergency_contact_phone: str | None = None

    def validate_context(self) -> None:
        super().validate_context()
        missing = []
        for field_name in ("employee_code", "first_name", "last_name", "department_id", "position_id", "hire_date"):
            if not getattr(self, field_name):
                missing.append(field_name)
        if self.base_salary < Decimal("0") or self.daily_salary < Decimal("0"):
            raise ValueError("salary values cannot be negative")
        if missing:
            raise ValueError("Missing required employee field(s): " + ", ".join(missing))


@dataclass(frozen=True)
class UpdateEmployeeCommand(CreateEmployeeCommand):
    employee_id: str = ""

    def validate_context(self) -> None:
        super().validate_context()
        if not self.employee_id:
            raise ValueError("employee_id is required")


@dataclass(frozen=True)
class DeactivateEmployeeCommand(BaseCommand):
    employee_id: str = ""
    termination_date: date | None = None
    termination_reason: str = ""

    def validate_context(self) -> None:
        super().validate_context()
        if not self.employee_id:
            raise ValueError("employee_id is required")
        if not self.termination_reason.strip():
            raise ValueError("termination_reason is required")


@dataclass(frozen=True)
class CreateDepartmentCommand(BaseCommand):
    name: str = ""

    def validate_context(self) -> None:
        super().validate_context()
        if not self.name.strip():
            raise ValueError("department name is required")


@dataclass(frozen=True)
class CreatePositionCommand(BaseCommand):
    name: str = ""
    department_id: str = ""

    def validate_context(self) -> None:
        super().validate_context()
        if not self.name.strip():
            raise ValueError("position name is required")
        if not self.department_id:
            raise ValueError("department_id is required")


@dataclass(frozen=True)
class CreateContractTypeCommand(BaseCommand):
    code: str = ""
    name: str = ""

    def validate_context(self) -> None:
        super().validate_context()
        if not self.code.strip() or not self.name.strip():
            raise ValueError("contract type code and name are required")


@dataclass(frozen=True)
class CreatePaymentFrequencyCommand(BaseCommand):
    code: str = ""
    name: str = ""

    def validate_context(self) -> None:
        super().validate_context()
        if not self.code.strip() or not self.name.strip():
            raise ValueError("payment frequency code and name are required")


@dataclass(frozen=True)
class CreateShiftCommand(BaseCommand):
    name: str = ""
    start_time: time | None = None
    end_time: time | None = None
    crosses_midnight: bool = False
    break_minutes: int = 0
    late_tolerance_minutes: int = 0

    def validate_context(self) -> None:
        super().validate_context()
        if not self.name.strip():
            raise ValueError("shift name is required")
        if self.start_time is None or self.end_time is None:
            raise ValueError("start_time and end_time are required")
        if self.break_minutes < 0 or self.late_tolerance_minutes < 0:
            raise ValueError("shift minutes cannot be negative")


@dataclass(frozen=True)
class AssignShiftCommand(BaseCommand):
    employee_id: str = ""
    work_shift_id: str = ""
    effective_from: date | None = None
    effective_to: date | None = None
    weekdays: str = ""

    def validate_context(self) -> None:
        super().validate_context()
        if not self.employee_id or not self.work_shift_id:
            raise ValueError("employee_id and work_shift_id are required")
        if self.effective_from is None:
            raise ValueError("effective_from is required")
        if not self.weekdays.strip():
            raise ValueError("weekdays is required")


@dataclass(frozen=True)
class CreateShiftTemplateCommand(BaseCommand):
    name: str = ""
    work_shift_id: str = ""
    weekdays: str = ""

    def validate_context(self) -> None:
        super().validate_context()
        if not self.name.strip() or not self.work_shift_id or not self.weekdays.strip():
            raise ValueError("template name, work_shift_id and weekdays are required")


@dataclass(frozen=True)
class CreateRestDayCommand(BaseCommand):
    employee_id: str = ""
    rest_date: date | None = None
    reason: str = ""

    def validate_context(self) -> None:
        super().validate_context()
        if not self.employee_id:
            raise ValueError("employee_id is required")
        if self.rest_date is None:
            raise ValueError("rest_date is required")
        if not self.reason.strip():
            raise ValueError("reason is required")


@dataclass(frozen=True)
class RequestLeaveCommand(BaseCommand):
    employee_id: str = ""
    leave_type: LeaveType = LeaveType.VACATION
    start_date: date | None = None
    end_date: date | None = None
    reason: str = ""

    def validate_context(self) -> None:
        super().validate_context()
        if not self.employee_id:
            raise ValueError("employee_id is required")
        if self.start_date is None or self.end_date is None:
            raise ValueError("start_date and end_date are required")
        if self.end_date < self.start_date:
            raise ValueError("end_date cannot be before start_date")
        if not self.reason.strip():
            raise ValueError("reason is required")


@dataclass(frozen=True)
class ApproveLeaveCommand(BaseCommand):
    leave_request_id: str = ""

    def validate_context(self) -> None:
        super().validate_context()
        if not self.leave_request_id:
            raise ValueError("leave_request_id is required")


@dataclass(frozen=True)
class RejectLeaveCommand(BaseCommand):
    leave_request_id: str = ""
    reason: str = ""

    def validate_context(self) -> None:
        super().validate_context()
        if not self.leave_request_id:
            raise ValueError("leave_request_id is required")
        if not self.reason.strip():
            raise ValueError("reason is required")


@dataclass(frozen=True)
class CancelLeaveCommand(BaseCommand):
    leave_request_id: str = ""
    reason: str = ""

    def validate_context(self) -> None:
        super().validate_context()
        if not self.leave_request_id:
            raise ValueError("leave_request_id is required")
        if not self.reason.strip():
            raise ValueError("reason is required")


@dataclass(frozen=True)
class GeneratePayrollRunCommand(BaseCommand):
    period_start: date | None = None
    period_end: date | None = None
    employee_ids: tuple[str, ...] = ()

    def validate_context(self) -> None:
        super().validate_context()
        if self.period_start is None or self.period_end is None:
            raise ValueError("period_start and period_end are required")
        if self.period_end < self.period_start:
            raise ValueError("period_end cannot be before period_start")
        if not self.employee_ids:
            raise ValueError("employee_ids are required")


@dataclass(frozen=True)
class AuthorizePayrollRunCommand(BaseCommand):
    payroll_run_id: str = ""

    def validate_context(self) -> None:
        super().validate_context()
        if not self.payroll_run_id:
            raise ValueError("payroll_run_id is required")


@dataclass(frozen=True)
class PayPayrollRunCommand(BaseCommand):
    payroll_run_id: str = ""
    payment_method: str = "CASH"

    def validate_context(self) -> None:
        super().validate_context()
        if not self.payroll_run_id:
            raise ValueError("payroll_run_id is required")
        if not self.payment_method.strip():
            raise ValueError("payment_method is required")


@dataclass(frozen=True)
class CancelPayrollRunCommand(BaseCommand):
    payroll_run_id: str = ""
    reason: str = ""

    def validate_context(self) -> None:
        super().validate_context()
        if not self.payroll_run_id:
            raise ValueError("payroll_run_id is required")
        if not self.reason.strip():
            raise ValueError("reason is required")
