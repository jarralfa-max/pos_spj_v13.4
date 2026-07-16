"""Employee, Department and Position repositories."""

from __future__ import annotations

from datetime import date

from backend.domain.hr.entities import Department, Employee, Position
from backend.domain.hr.enums import ContractType, EmploymentStatus, PaymentFrequency
from backend.domain.hr.value_objects import Money
from backend.infrastructure.db.repositories.hr.base import HRRepositoryBase

_EMP_COLS = (
    "id, employee_code, first_name, last_name, phone_e164, email, branch_id,"
    " department_id, position_id, supervisor_employee_id, employment_status,"
    " contract_type, payment_frequency, base_salary, daily_salary, currency_code,"
    " hire_date, termination_date, termination_reason, bank_account_reference,"
    " tax_identifier, emergency_contact_name, emergency_contact_phone, active,"
    " created_at, updated_at"
)


def _emp_to_entity(row: dict) -> Employee:
    currency = row["currency_code"]
    return Employee(
        id=row["id"], employee_code=row["employee_code"],
        first_name=row["first_name"], last_name=row["last_name"],
        branch_id=row["branch_id"],
        employment_status=EmploymentStatus(row["employment_status"]),
        contract_type=ContractType(row["contract_type"]),
        payment_frequency=PaymentFrequency(row["payment_frequency"]),
        base_salary=Money.from_string(row["base_salary"], currency),
        daily_salary=Money.from_string(row["daily_salary"], currency),
        hire_date=date.fromisoformat(row["hire_date"]),
        phone_e164=row["phone_e164"], email=row["email"],
        department_id=row["department_id"], position_id=row["position_id"],
        supervisor_employee_id=row["supervisor_employee_id"],
        termination_date=(date.fromisoformat(row["termination_date"])
                          if row["termination_date"] else None),
        termination_reason=row["termination_reason"],
        bank_account_reference=row["bank_account_reference"],
        tax_identifier=row["tax_identifier"],
        emergency_contact_name=row["emergency_contact_name"],
        emergency_contact_phone=row["emergency_contact_phone"],
        active=bool(row["active"]),
        created_at=row["created_at"], updated_at=row["updated_at"],
    )


class EmployeeRepository(HRRepositoryBase):
    def save(self, employee: Employee) -> None:
        self._execute(
            f"INSERT INTO employees ({_EMP_COLS})"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (employee.id, employee.employee_code, employee.first_name, employee.last_name,
             employee.phone_e164, employee.email, employee.branch_id,
             employee.department_id, employee.position_id, employee.supervisor_employee_id,
             employee.employment_status.value, employee.contract_type.value,
             employee.payment_frequency.value, employee.base_salary.to_string(),
             employee.daily_salary.to_string(), employee.base_salary.currency_code,
             employee.hire_date.isoformat(),
             employee.termination_date.isoformat() if employee.termination_date else None,
             employee.termination_reason, employee.bank_account_reference,
             employee.tax_identifier, employee.emergency_contact_name,
             employee.emergency_contact_phone, int(employee.active),
             employee.created_at, employee.updated_at),
        )

    def update(self, employee: Employee) -> None:
        self._execute(
            "UPDATE employees SET first_name=?, last_name=?, phone_e164=?, email=?,"
            " department_id=?, position_id=?, supervisor_employee_id=?,"
            " employment_status=?, contract_type=?, payment_frequency=?, base_salary=?,"
            " daily_salary=?, termination_date=?, termination_reason=?,"
            " bank_account_reference=?, tax_identifier=?, emergency_contact_name=?,"
            " emergency_contact_phone=?, active=?, updated_at=? WHERE id=?",
            (employee.first_name, employee.last_name, employee.phone_e164, employee.email,
             employee.department_id, employee.position_id, employee.supervisor_employee_id,
             employee.employment_status.value, employee.contract_type.value,
             employee.payment_frequency.value, employee.base_salary.to_string(),
             employee.daily_salary.to_string(),
             employee.termination_date.isoformat() if employee.termination_date else None,
             employee.termination_reason, employee.bank_account_reference,
             employee.tax_identifier, employee.emergency_contact_name,
             employee.emergency_contact_phone, int(employee.active),
             employee.updated_at, employee.id),
        )

    def get(self, employee_id: str) -> Employee | None:
        row = self._query_one(f"SELECT {_EMP_COLS} FROM employees WHERE id=?", (employee_id,))
        return _emp_to_entity(row) if row else None

    def get_by_code(self, employee_code: str) -> Employee | None:
        row = self._query_one(
            f"SELECT {_EMP_COLS} FROM employees WHERE employee_code=?", (employee_code,))
        return _emp_to_entity(row) if row else None

    def get_by_user_id(self, user_id: str) -> Employee | None:
        row = self._query_one(
            f"SELECT {_EMP_COLS} FROM employees WHERE id="
            " (SELECT personal_id FROM usuarios WHERE id=?)", (user_id,))
        return _emp_to_entity(row) if row else None

    def list_active(self, *, branch_id: str | None = None) -> list[Employee]:
        if branch_id:
            rows = self._query(
                f"SELECT {_EMP_COLS} FROM employees WHERE active=1 AND branch_id=?"
                " ORDER BY last_name, first_name", (branch_id,))
        else:
            rows = self._query(
                f"SELECT {_EMP_COLS} FROM employees WHERE active=1"
                " ORDER BY last_name, first_name")
        return [_emp_to_entity(r) for r in rows]

    def list_all(self, *, limit: int = 200, offset: int = 0) -> list[Employee]:
        rows = self._query(
            f"SELECT {_EMP_COLS} FROM employees ORDER BY last_name, first_name"
            " LIMIT ? OFFSET ?", (limit, offset))
        return [_emp_to_entity(r) for r in rows]

    def link_user(self, user_id: str, employee_id: str) -> None:
        """Link a system user to an employee via usuarios.personal_id (mig 095)."""
        self._execute("UPDATE usuarios SET personal_id=? WHERE id=?", (employee_id, user_id))


class DepartmentRepository(HRRepositoryBase):
    def save(self, department: Department) -> None:
        self._execute(
            "INSERT INTO hr_departments (id, code, name, branch_id, active, created_at)"
            " VALUES (?,?,?,?,?,?)",
            (department.id, department.code, department.name, department.branch_id,
             int(department.active), department.created_at))

    def get(self, department_id: str) -> Department | None:
        row = self._query_one(
            "SELECT id, code, name, branch_id, active, created_at"
            " FROM hr_departments WHERE id=?", (department_id,))
        return Department(id=row["id"], code=row["code"], name=row["name"],
                          branch_id=row["branch_id"], active=bool(row["active"]),
                          created_at=row["created_at"]) if row else None

    def list_active(self) -> list[Department]:
        rows = self._query(
            "SELECT id, code, name, branch_id, active, created_at"
            " FROM hr_departments WHERE active=1 ORDER BY name")
        return [Department(id=r["id"], code=r["code"], name=r["name"],
                           branch_id=r["branch_id"], active=bool(r["active"]),
                           created_at=r["created_at"]) for r in rows]


class PositionRepository(HRRepositoryBase):
    def save(self, position: Position) -> None:
        self._execute(
            "INSERT INTO hr_positions (id, code, name, department_id, active, created_at)"
            " VALUES (?,?,?,?,?,?)",
            (position.id, position.code, position.name, position.department_id,
             int(position.active), position.created_at))

    def get(self, position_id: str) -> Position | None:
        row = self._query_one(
            "SELECT id, code, name, department_id, active, created_at"
            " FROM hr_positions WHERE id=?", (position_id,))
        return Position(id=row["id"], code=row["code"], name=row["name"],
                        department_id=row["department_id"], active=bool(row["active"]),
                        created_at=row["created_at"]) if row else None

    def list_active(self) -> list[Position]:
        rows = self._query(
            "SELECT id, code, name, department_id, active, created_at"
            " FROM hr_positions WHERE active=1 ORDER BY name")
        return [Position(id=r["id"], code=r["code"], name=r["name"],
                         department_id=r["department_id"], active=bool(r["active"]),
                         created_at=r["created_at"]) for r in rows]
