"""SQLite repository for HR payroll payments."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from sqlite3 import Connection

from backend.domain.hr.entities import PayrollPayment


class SQLitePayrollPaymentRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def save(self, payroll_payment: PayrollPayment) -> None:
        self._connection.execute(
            """
            INSERT INTO payroll_payments (
                id, payroll_run_id, branch_id, payment_method, net_amount,
                operation_id, paid_by_user_id, paid_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(operation_id) DO NOTHING
            """,
            self._params(payroll_payment),
        )

    def get_by_operation_id(self, operation_id: str) -> PayrollPayment | None:
        row = self._connection.execute(
            """
            SELECT id, payroll_run_id, branch_id, payment_method, net_amount, operation_id, paid_by_user_id, paid_at
            FROM payroll_payments
            WHERE operation_id = ?
            """,
            (operation_id,),
        ).fetchone()
        return self._row_to_payment(row) if row else None

    def get_by_run_id(self, payroll_run_id: str) -> PayrollPayment | None:
        row = self._connection.execute(
            """
            SELECT id, payroll_run_id, branch_id, payment_method, net_amount, operation_id, paid_by_user_id, paid_at
            FROM payroll_payments
            WHERE payroll_run_id = ?
            """,
            (payroll_run_id,),
        ).fetchone()
        return self._row_to_payment(row) if row else None

    def _params(self, payroll_payment: PayrollPayment) -> tuple[object, ...]:
        return (
            payroll_payment.id,
            payroll_payment.payroll_run_id,
            payroll_payment.branch_id,
            payroll_payment.payment_method,
            str(payroll_payment.net_amount),
            payroll_payment.operation_id,
            payroll_payment.paid_by_user_id,
            payroll_payment.paid_at.isoformat(),
        )

    def _row_to_payment(self, row) -> PayrollPayment:
        return PayrollPayment(
            id=row[0],
            payroll_run_id=row[1],
            branch_id=row[2],
            payment_method=row[3],
            net_amount=Decimal(str(row[4])),
            operation_id=row[5],
            paid_by_user_id=row[6],
            paid_at=datetime.fromisoformat(row[7]),
        )
