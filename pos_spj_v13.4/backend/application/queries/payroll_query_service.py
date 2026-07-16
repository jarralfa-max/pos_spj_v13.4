"""Read-only query service for HR payroll runs."""

from __future__ import annotations

from decimal import Decimal
from sqlite3 import Connection

from backend.application.dto.payroll_dto import PayrollLineDTO, PayrollPaymentDTO, PayrollRunDTO


class PayrollQueryService:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def list_runs(self, *, branch_id: str | None = None, limit: int = 50, offset: int = 0) -> list[PayrollRunDTO]:
        params: list[object] = []
        where = ""
        if branch_id:
            where = "WHERE branch_id = ?"
            params.append(branch_id)
        params.extend([limit, offset])
        rows = self._connection.execute(
            """
            SELECT id, branch_id, period_start, period_end, status,
                   gross_amount, deductions_amount, net_amount
            FROM payroll_runs
            """
            + where
            + " ORDER BY period_start DESC LIMIT ? OFFSET ?",
            tuple(params),
        ).fetchall()
        return [
            PayrollRunDTO(
                id=row[0], branch_id=row[1], period_start=row[2], period_end=row[3],
                status=row[4], gross_amount=Decimal(str(row[5])),
                deductions_amount=Decimal(str(row[6])), net_amount=Decimal(str(row[7])),
            )
            for row in rows
        ]

    def list_lines(self, *, payroll_run_id: str) -> list[PayrollLineDTO]:
        rows = self._connection.execute(
            """
            SELECT id, payroll_run_id, employee_id, gross_amount, deductions_amount, net_amount
            FROM payroll_lines
            WHERE payroll_run_id = ?
            ORDER BY employee_id
            """,
            (payroll_run_id,),
        ).fetchall()
        return [PayrollLineDTO(id=row[0], payroll_run_id=row[1], employee_id=row[2], gross_amount=Decimal(str(row[3])), deductions_amount=Decimal(str(row[4])), net_amount=Decimal(str(row[5]))) for row in rows]

    def list_payments(self, *, payroll_run_id: str | None = None) -> list[PayrollPaymentDTO]:
        params: list[object] = []
        where = ""
        if payroll_run_id:
            where = "WHERE payroll_run_id = ?"
            params.append(payroll_run_id)
        rows = self._connection.execute(
            """
            SELECT id, payroll_run_id, branch_id, payment_method, net_amount, operation_id, paid_by_user_id, paid_at
            FROM payroll_payments
            """
            + where
            + " ORDER BY paid_at DESC",
            tuple(params),
        ).fetchall()
        return [PayrollPaymentDTO(id=row[0], payroll_run_id=row[1], branch_id=row[2], payment_method=row[3], net_amount=Decimal(str(row[4])), operation_id=row[5], paid_by_user_id=row[6], paid_at=row[7]) for row in rows]
