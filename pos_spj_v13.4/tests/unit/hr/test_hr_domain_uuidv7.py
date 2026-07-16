from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from backend.domain.hr.entities import Employee
from backend.domain.hr.enums import ContractType, PaymentFrequency


def test_employee_identity_is_uuidv7_string() -> None:
    employee = Employee(
        employee_code="EMP-001",
        first_name="Ana",
        last_name="Pérez",
        branch_id="01900000-0000-7000-8000-000000000001",
        department_id="01900000-0000-7000-8000-000000000101",
        position_id="01900000-0000-7000-8000-000000000201",
        contract_type=ContractType.FULL_TIME,
        payment_frequency=PaymentFrequency.WEEKLY,
        base_salary=Decimal("1000"),
        daily_salary=Decimal("200"),
        hire_date=date(2026, 1, 1),
    )

    parsed = UUID(employee.id)
    assert isinstance(employee.id, str)
    assert parsed.version == 7
