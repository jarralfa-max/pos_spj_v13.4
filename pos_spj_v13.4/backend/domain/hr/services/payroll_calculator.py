"""PayrollCalculator — builds payroll lines for employees over a period.

Pure computation: given an employee's salary, attendance summary and manual
concepts, it produces the ``PayrollLine`` list. No SQL, no repositories.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.domain.hr.entities import Employee, PayrollLine
from backend.domain.hr.enums import DEDUCTION_CONCEPTS, PayrollConcept
from backend.domain.hr.value_objects import Money


@dataclass(frozen=True, slots=True)
class EmployeePayrollInput:
    employee: Employee
    worked_days: int
    overtime_minutes: int = 0
    late_minutes: int = 0
    absence_days: int = 0
    extra_concepts: tuple[tuple[PayrollConcept, Money], ...] = ()


class PayrollCalculator:
    def __init__(self, *, overtime_multiplier: str = "1.5") -> None:
        self._overtime_multiplier = Decimal(overtime_multiplier)

    def build_lines(self, payroll_run_id: str, item: EmployeePayrollInput) -> list[PayrollLine]:
        employee = item.employee
        lines: list[PayrollLine] = []

        base = employee.daily_salary.multiply(item.worked_days)
        lines.append(PayrollLine.create(
            payroll_run_id, employee.id, PayrollConcept.BASE_SALARY, base,
            is_deduction=False, quantity=str(item.worked_days)))

        if item.overtime_minutes > 0:
            minute_rate = employee.daily_salary.multiply(Decimal("1") / Decimal("480"))
            overtime = minute_rate.multiply(
                Decimal(item.overtime_minutes) * self._overtime_multiplier)
            lines.append(PayrollLine.create(
                payroll_run_id, employee.id, PayrollConcept.OVERTIME, overtime,
                is_deduction=False, quantity=str(item.overtime_minutes)))

        if item.absence_days > 0:
            deduction = employee.daily_salary.multiply(item.absence_days)
            lines.append(PayrollLine.create(
                payroll_run_id, employee.id, PayrollConcept.ABSENCE_DEDUCTION, deduction,
                is_deduction=True, quantity=str(item.absence_days)))

        if item.late_minutes > 0:
            minute_rate = employee.daily_salary.multiply(Decimal("1") / Decimal("480"))
            late_deduction = minute_rate.multiply(item.late_minutes)
            lines.append(PayrollLine.create(
                payroll_run_id, employee.id, PayrollConcept.LATE_DEDUCTION, late_deduction,
                is_deduction=True, quantity=str(item.late_minutes)))

        for concept, amount in item.extra_concepts:
            lines.append(PayrollLine.create(
                payroll_run_id, employee.id, concept, amount,
                is_deduction=concept in DEDUCTION_CONCEPTS))
        return lines
