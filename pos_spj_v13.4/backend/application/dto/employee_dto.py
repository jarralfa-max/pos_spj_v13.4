"""Employee DTOs for HR query/application boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class EmployeeDTO:
    id: str
    employee_code: str
    first_name: str
    last_name: str
    branch_id: str
    department_id: str
    position_id: str
    employment_status: str
    contract_type: str
    payment_frequency: str
    base_salary: Decimal
    daily_salary: Decimal
    hire_date: str
    active: bool

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()
