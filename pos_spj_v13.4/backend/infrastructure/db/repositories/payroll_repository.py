"""SQLite repository for HR payroll runs, lines and concepts."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from sqlite3 import Connection

from backend.domain.hr.entities import PayrollConcept, PayrollLine, PayrollRun
from backend.domain.hr.enums import PayrollConceptCode, PayrollRunStatus


class SQLitePayrollRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def save_run(self, payroll_run: PayrollRun) -> None:
        self._connection.execute(
            """
            INSERT INTO payroll_runs (
                id, branch_id, period_start, period_end, status, gross_amount,
                deductions_amount, net_amount, operation_id, authorized_by_user_id,
                paid_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(operation_id) DO NOTHING
            """,
            self._run_params(payroll_run),
        )

    def update_run(self, payroll_run: PayrollRun) -> None:
        self._connection.execute(
            """
            UPDATE payroll_runs
            SET status = ?, gross_amount = ?, deductions_amount = ?, net_amount = ?,
                authorized_by_user_id = ?, paid_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                payroll_run.status.value,
                str(payroll_run.gross_amount),
                str(payroll_run.deductions_amount),
                str(payroll_run.net_amount),
                payroll_run.authorized_by_user_id,
                payroll_run.paid_at.isoformat() if payroll_run.paid_at else None,
                payroll_run.updated_at.isoformat(),
                payroll_run.id,
            ),
        )

    def get_run(self, payroll_run_id: str) -> PayrollRun | None:
        row = self._connection.execute(
            """
            SELECT id, branch_id, period_start, period_end, status, gross_amount,
                   deductions_amount, net_amount, operation_id, authorized_by_user_id,
                   paid_at, created_at, updated_at
            FROM payroll_runs
            WHERE id = ?
            """,
            (payroll_run_id,),
        ).fetchone()
        return self._row_to_run(row) if row else None

    def get_run_by_operation_id(self, operation_id: str) -> PayrollRun | None:
        row = self._connection.execute(
            """
            SELECT id, branch_id, period_start, period_end, status, gross_amount,
                   deductions_amount, net_amount, operation_id, authorized_by_user_id,
                   paid_at, created_at, updated_at
            FROM payroll_runs
            WHERE operation_id = ?
            """,
            (operation_id,),
        ).fetchone()
        return self._row_to_run(row) if row else None

    def save_line(self, payroll_line: PayrollLine) -> None:
        self._connection.execute(
            """
            INSERT INTO payroll_lines (
                id, payroll_run_id, employee_id, gross_amount, deductions_amount, net_amount
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(payroll_run_id, employee_id) DO UPDATE SET
                gross_amount = excluded.gross_amount,
                deductions_amount = excluded.deductions_amount,
                net_amount = excluded.net_amount
            """,
            (
                payroll_line.id,
                payroll_line.payroll_run_id,
                payroll_line.employee_id,
                str(payroll_line.gross_amount),
                str(payroll_line.deductions_amount),
                str(payroll_line.net_amount),
            ),
        )

    def list_lines(self, payroll_run_id: str) -> list[PayrollLine]:
        rows = self._connection.execute(
            """
            SELECT id, payroll_run_id, employee_id, gross_amount, deductions_amount, net_amount
            FROM payroll_lines
            WHERE payroll_run_id = ?
            ORDER BY employee_id
            """,
            (payroll_run_id,),
        ).fetchall()
        return [
            PayrollLine(id=row[0], payroll_run_id=row[1], employee_id=row[2], gross_amount=Decimal(str(row[3])), deductions_amount=Decimal(str(row[4])), net_amount=Decimal(str(row[5])))
            for row in rows
        ]

    def save_concept(self, payroll_concept: PayrollConcept) -> None:
        self._connection.execute(
            """
            INSERT INTO payroll_concepts (id, payroll_line_id, concept_code, amount, notes)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                payroll_concept.id,
                payroll_concept.payroll_line_id,
                payroll_concept.concept_code.value,
                str(payroll_concept.amount),
                payroll_concept.notes,
            ),
        )

    def list_concepts(self, payroll_line_id: str) -> list[PayrollConcept]:
        rows = self._connection.execute(
            """
            SELECT id, payroll_line_id, concept_code, amount, notes
            FROM payroll_concepts
            WHERE payroll_line_id = ?
            ORDER BY concept_code
            """,
            (payroll_line_id,),
        ).fetchall()
        return [PayrollConcept(id=row[0], payroll_line_id=row[1], concept_code=PayrollConceptCode(row[2]), amount=Decimal(str(row[3])), notes=row[4]) for row in rows]

    def _run_params(self, payroll_run: PayrollRun) -> tuple[object, ...]:
        return (
            payroll_run.id,
            payroll_run.branch_id,
            payroll_run.period_start.isoformat(),
            payroll_run.period_end.isoformat(),
            payroll_run.status.value,
            str(payroll_run.gross_amount),
            str(payroll_run.deductions_amount),
            str(payroll_run.net_amount),
            payroll_run.operation_id,
            payroll_run.authorized_by_user_id,
            payroll_run.paid_at.isoformat() if payroll_run.paid_at else None,
            payroll_run.created_at.isoformat(),
            payroll_run.updated_at.isoformat(),
        )

    def _row_to_run(self, row) -> PayrollRun:
        return PayrollRun(
            id=row[0],
            branch_id=row[1],
            period_start=date.fromisoformat(row[2]),
            period_end=date.fromisoformat(row[3]),
            status=PayrollRunStatus(row[4]),
            gross_amount=Decimal(str(row[5])),
            deductions_amount=Decimal(str(row[6])),
            net_amount=Decimal(str(row[7])),
            operation_id=row[8],
            authorized_by_user_id=row[9],
            paid_at=datetime.fromisoformat(row[10]) if row[10] else None,
            created_at=datetime.fromisoformat(row[11]),
            updated_at=datetime.fromisoformat(row[12]),
        )
