"""Payroll DTOs for HR query/application boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class PayrollRunDTO:
    id: str
    branch_id: str
    period_start: str
    period_end: str
    status: str
    gross_amount: Decimal
    deductions_amount: Decimal
    net_amount: Decimal


@dataclass(frozen=True, slots=True)
class PayrollLineDTO:
    id: str
    payroll_run_id: str
    employee_id: str
    gross_amount: Decimal
    deductions_amount: Decimal
    net_amount: Decimal


@dataclass(frozen=True, slots=True)
class PayrollPaymentDTO:
    id: str
    payroll_run_id: str
    branch_id: str
    payment_method: str
    net_amount: Decimal
    operation_id: str
    paid_by_user_id: str
    paid_at: str
