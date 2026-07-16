"""Read-only query service for canonical HR employees."""

from __future__ import annotations

from decimal import Decimal
from sqlite3 import Connection

from backend.application.dto.employee_dto import EmployeeDTO


class HREmployeeQueryService:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def list_employees(self, *, search: str | None = None, limit: int = 50, offset: int = 0) -> list[EmployeeDTO]:
        params: list[object] = []
        where = ""
        if search:
            where = "WHERE first_name LIKE ? OR last_name LIKE ? OR employee_code LIKE ?"
            token = f"%{search}%"
            params.extend([token, token, token])
        params.extend([limit, offset])
        rows = self._connection.execute(
            f"""
            SELECT id, employee_code, first_name, last_name, branch_id,
                   department_id, position_id, employment_status, contract_type,
                   payment_frequency, base_salary, daily_salary, hire_date, active
            FROM employees
            {where}
            ORDER BY employee_code
            LIMIT ? OFFSET ?
            """,
            params,
        ).fetchall()
        return [self._to_dto(row) for row in rows]


    def get_employee(self, employee_id: str) -> EmployeeDTO | None:
        row = self._connection.execute(
            """
            SELECT id, employee_code, first_name, last_name, branch_id,
                   department_id, position_id, employment_status, contract_type,
                   payment_frequency, base_salary, daily_salary, hire_date, active
            FROM employees
            WHERE id = ?
            """,
            (employee_id,),
        ).fetchone()
        return self._to_dto(row) if row is not None else None

    def _to_dto(self, row) -> EmployeeDTO:
        return EmployeeDTO(
            id=row[0],
            employee_code=row[1],
            first_name=row[2],
            last_name=row[3],
            branch_id=row[4],
            department_id=row[5],
            position_id=row[6],
            employment_status=row[7],
            contract_type=row[8],
            payment_frequency=row[9],
            base_salary=Decimal(str(row[10])),
            daily_salary=Decimal(str(row[11])),
            hire_date=row[12],
            active=bool(row[13]),
        )
