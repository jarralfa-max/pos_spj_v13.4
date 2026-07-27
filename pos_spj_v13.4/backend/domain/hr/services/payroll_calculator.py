"""Domain service for payroll calculations."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from backend.domain.hr.entities import Employee


class PayrollCalculator:
    def gross_salary_for_period(self, employee: Employee, period_start: date, period_end: date) -> Decimal:
        days = Decimal((period_end - period_start).days + 1)
        return max(employee.daily_salary * days, Decimal("0"))

    def net_amount(self, gross_amount: Decimal, deductions_amount: Decimal) -> Decimal:
        net = gross_amount - deductions_amount
        return net if net > Decimal("0") else Decimal("0")
