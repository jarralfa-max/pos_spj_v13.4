"""SQLite implementation of the HR employee repository port."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from sqlite3 import Connection

from backend.domain.hr.entities import Employee
from backend.domain.hr.enums import ContractType, EmploymentStatus, PaymentFrequency


class SQLiteEmployeeRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def get(self, employee_id: str) -> Employee | None:
        row = self._connection.execute(
            """
            SELECT id, employee_code, first_name, last_name, phone_e164, email,
                   branch_id, department_id, position_id, supervisor_employee_id,
                   employment_status, contract_type, payment_frequency,
                   base_salary, daily_salary, hire_date, termination_date,
                   termination_reason, bank_account_reference, tax_identifier,
                   emergency_contact_name, emergency_contact_phone, active,
                   created_at, updated_at
            FROM employees
            WHERE id = ?
            """,
            (employee_id,),
        ).fetchone()
        if row is None:
            return None
        return self._from_row(row)

    def save(self, employee: Employee) -> None:
        self._connection.execute(
            """
            INSERT INTO employees (
                id, employee_code, first_name, last_name, phone_e164, email,
                branch_id, department_id, position_id, supervisor_employee_id,
                employment_status, contract_type, payment_frequency,
                base_salary, daily_salary, hire_date, termination_date,
                termination_reason, bank_account_reference, tax_identifier,
                emergency_contact_name, emergency_contact_phone, active,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                employee_code = excluded.employee_code,
                first_name = excluded.first_name,
                last_name = excluded.last_name,
                phone_e164 = excluded.phone_e164,
                email = excluded.email,
                branch_id = excluded.branch_id,
                department_id = excluded.department_id,
                position_id = excluded.position_id,
                supervisor_employee_id = excluded.supervisor_employee_id,
                employment_status = excluded.employment_status,
                contract_type = excluded.contract_type,
                payment_frequency = excluded.payment_frequency,
                base_salary = excluded.base_salary,
                daily_salary = excluded.daily_salary,
                hire_date = excluded.hire_date,
                termination_date = excluded.termination_date,
                termination_reason = excluded.termination_reason,
                bank_account_reference = excluded.bank_account_reference,
                tax_identifier = excluded.tax_identifier,
                emergency_contact_name = excluded.emergency_contact_name,
                emergency_contact_phone = excluded.emergency_contact_phone,
                active = excluded.active,
                updated_at = excluded.updated_at
            """,
            self._to_params(employee),
        )

    def _to_params(self, employee: Employee) -> tuple[object, ...]:
        return (
            employee.id,
            employee.employee_code,
            employee.first_name,
            employee.last_name,
            employee.phone_e164,
            employee.email,
            employee.branch_id,
            employee.department_id,
            employee.position_id,
            employee.supervisor_employee_id,
            employee.employment_status.value,
            employee.contract_type.value,
            employee.payment_frequency.value,
            str(employee.base_salary),
            str(employee.daily_salary),
            employee.hire_date.isoformat(),
            employee.termination_date.isoformat() if employee.termination_date else None,
            employee.termination_reason,
            employee.bank_account_reference,
            employee.tax_identifier,
            employee.emergency_contact_name,
            employee.emergency_contact_phone,
            1 if employee.active else 0,
            employee.created_at.isoformat(),
            employee.updated_at.isoformat(),
        )

    def _from_row(self, row) -> Employee:
        return Employee(
            id=row[0],
            employee_code=row[1],
            first_name=row[2],
            last_name=row[3],
            phone_e164=row[4],
            email=row[5],
            branch_id=row[6],
            department_id=row[7],
            position_id=row[8],
            supervisor_employee_id=row[9],
            employment_status=EmploymentStatus(row[10]),
            contract_type=ContractType(row[11]),
            payment_frequency=PaymentFrequency(row[12]),
            base_salary=Decimal(str(row[13])),
            daily_salary=Decimal(str(row[14])),
            hire_date=date.fromisoformat(row[15]),
            termination_date=date.fromisoformat(row[16]) if row[16] else None,
            termination_reason=row[17],
            bank_account_reference=row[18],
            tax_identifier=row[19],
            emergency_contact_name=row[20],
            emergency_contact_phone=row[21],
            active=bool(row[22]),
            created_at=datetime.fromisoformat(row[23]),
            updated_at=datetime.fromisoformat(row[24]),
        )
