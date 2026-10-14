"""Repositorios de apoyo agregados por la auditoría d9f2bca de Finanzas.

- ``ReceivableChargeRepository`` (F03): cargos a crédito con identidad estable.
- ``ExpenseRequestRepository`` (F15): solicitudes de gasto identificables.
- ``CloseExceptionRepository`` (F16): diferencias materiales por periodo.
"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.infrastructure.db.repositories.finance.base import FinanceRepositoryBase
from backend.shared.ids import new_uuid


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ReceivableChargeRepository(FinanceRepositoryBase):
    def find_by_operation_id(self, operation_id: str) -> dict | None:
        return self._query_one(
            "SELECT id, receivable_id, amount, currency_code, source_module,"
            " source_reference, operation_id, created_at"
            " FROM receivable_charges WHERE operation_id=?", (operation_id,))

    def add(self, *, receivable_id: str, amount: str, currency_code: str,
            source_module: str, source_reference: str, operation_id: str) -> str:
        charge_id = new_uuid()
        self._execute(
            "INSERT INTO receivable_charges (id, receivable_id, amount, currency_code,"
            " source_module, source_reference, operation_id, created_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (charge_id, receivable_id, amount, currency_code, source_module,
             source_reference, operation_id, _now()))
        return charge_id

    def list_by_receivable(self, receivable_id: str) -> list[dict]:
        return self._query(
            "SELECT id, amount, currency_code, source_reference, operation_id, created_at"
            " FROM receivable_charges WHERE receivable_id=? ORDER BY created_at",
            (receivable_id,))


_EXPENSE_COLUMNS = ("id, budget_id, account_id, period_code, cost_center_id, branch_id,"
                    " amount, currency_code, status, requested_by, resolved_by,"
                    " resolution_reference, resolution_reason, operation_id, created_at,"
                    " updated_at")


class ExpenseRequestRepository(FinanceRepositoryBase):
    def find_by_operation_id(self, operation_id: str) -> dict | None:
        return self._query_one(
            f"SELECT {_EXPENSE_COLUMNS} FROM expense_requests WHERE operation_id=?",
            (operation_id,))

    def get(self, request_id: str) -> dict | None:
        return self._query_one(
            f"SELECT {_EXPENSE_COLUMNS} FROM expense_requests WHERE id=?", (request_id,))

    def add(self, *, budget_id: str, account_id: str, period_code: str,
            cost_center_id: str | None, branch_id: str | None, amount: str,
            currency_code: str, requested_by: str | None, operation_id: str) -> str:
        request_id = new_uuid()
        now = _now()
        self._execute(
            f"INSERT INTO expense_requests ({_EXPENSE_COLUMNS})"
            " VALUES (?,?,?,?,?,?,?,?,'COMMITTED',?,NULL,NULL,NULL,?,?,?)",
            (request_id, budget_id, account_id, period_code, cost_center_id, branch_id,
             amount, currency_code, requested_by, operation_id, now, now))
        return request_id

    def resolve(self, request_id: str, *, status: str, resolved_by: str | None,
                reference: str | None, reason: str | None) -> None:
        cursor = self._conn.execute(
            "UPDATE expense_requests SET status=?, resolved_by=?, resolution_reference=?,"
            " resolution_reason=?, updated_at=? WHERE id=? AND status='COMMITTED'",
            (status, resolved_by, reference, reason, _now(), request_id))
        if cursor.rowcount == 0:
            from backend.domain.finance.exceptions import ConcurrencyConflictError
            raise ConcurrencyConflictError(
                "La solicitud de gasto ya no está comprometida (otra operación la resolvió)")


class CloseExceptionRepository(FinanceRepositoryBase):
    def open_or_refresh(self, *, period_code: str, check_type: str, subject: str,
                        expected: str, actual: str, difference: str,
                        currency_code: str) -> str:
        """Una excepción ABIERTA por (periodo, control, sujeto): si ya existe se
        actualizan sus cifras en vez de duplicarla."""
        row = self._query_one(
            "SELECT id FROM finance_close_exceptions WHERE period_code=? AND check_type=?"
            " AND subject=? AND status='OPEN'", (period_code, check_type, subject))
        if row is not None:
            self._execute(
                "UPDATE finance_close_exceptions SET expected_amount=?, actual_amount=?,"
                " difference=?, detected_at=? WHERE id=?",
                (expected, actual, difference, _now(), row["id"]))
            return row["id"]
        exception_id = new_uuid()
        self._execute(
            "INSERT INTO finance_close_exceptions (id, period_code, check_type, subject,"
            " expected_amount, actual_amount, difference, currency_code, status, detected_at)"
            " VALUES (?,?,?,?,?,?,?,?,'OPEN',?)",
            (exception_id, period_code, check_type, subject, expected, actual, difference,
             currency_code, _now()))
        return exception_id

    def resolve_missing(self, *, period_code: str, check_type: str,
                        still_open_subjects: set[str]) -> None:
        """Al volver a medir, lo que ya no difiere queda RESUELTO solo."""
        for row in self._query(
                "SELECT id, subject FROM finance_close_exceptions WHERE period_code=?"
                " AND check_type=? AND status='OPEN'", (period_code, check_type)):
            if row["subject"] not in still_open_subjects:
                self._execute(
                    "UPDATE finance_close_exceptions SET status='RESOLVED', resolved_at=?,"
                    " resolution_reason=? WHERE id=?",
                    (_now(), "La diferencia desapareció al volver a medir", row["id"]))

    def list_open(self, period_code: str | None = None) -> list[dict]:
        """Abiertas; con ``period_code``, las de ese periodo y anteriores."""
        if period_code is None:
            return self._query(
                "SELECT * FROM finance_close_exceptions WHERE status='OPEN'"
                " ORDER BY period_code, check_type")
        return self._query(
            "SELECT * FROM finance_close_exceptions WHERE status='OPEN' AND period_code<=?"
            " ORDER BY period_code, check_type", (period_code,))

    def authorize(self, exception_id: str, *, authorized_by: str, reason: str) -> None:
        cursor = self._conn.execute(
            "UPDATE finance_close_exceptions SET status='AUTHORIZED', resolved_by=?,"
            " resolved_at=?, resolution_reason=? WHERE id=? AND status='OPEN'",
            (authorized_by, _now(), reason, exception_id))
        if cursor.rowcount == 0:
            from backend.domain.finance.exceptions import FinanceDomainError
            raise FinanceDomainError("La excepción no existe o ya no está abierta")
