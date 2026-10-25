"""Repositorios de apoyo agregados por la auditoría d9f2bca de Finanzas.

- ``ReceivableChargeRepository`` (F03): cargos a crédito con identidad estable.
- ``ExpenseRequestRepository`` (F15 / FIN-ERP §16): solicitudes de gasto, aprobaciones y reglas.
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


class ExpenseRequestRepository(FinanceRepositoryBase):
    """Solicitudes de gasto, sus aprobaciones y las reglas que fijan cuántas (§16)."""

    def save(self, request) -> None:
        values = {
            "id": request.id, "budget_id": request.budget_id, "account_id": request.account_id,
            "period_code": request.period_code, "category": request.category,
            "description": request.description, "cost_center_id": request.cost_center_id,
            "project_id": request.project_id, "department_id": request.department_id,
            "branch_id": request.branch_id, "supplier_id": request.supplier_id,
            "amount": request.amount.to_string(), "currency_code": request.amount.currency_code,
            "required_approvals": request.required_approvals,
            "requested_by": request.requested_by, "operation_id": request.operation_id,
            "created_at": request.created_at,
        }
        values.update(self._mutable(request))
        self._insert("expense_requests", values)
        self._sync_approvals(request)

    def update(self, request) -> None:
        self._update("expense_requests", self._mutable(request), where="id=?",
                     params=(request.id,))
        self._sync_approvals(request)

    @staticmethod
    def _mutable(request) -> dict:
        return {
            "status": request.status.value,
            "accrued_amount": request.accrued_amount.to_string(),
            "settled_amount": request.settled_amount.to_string(),
            "excess_authorized": int(request.excess_authorized),
            "resolution_reason": request.resolution_reason,
            "payable_id": request.payable_id,
            "accrual_journal_entry_id": request.accrual_journal_entry_id,
            "document_reference": request.document_reference,
            "updated_at": request.updated_at,
        }

    def _sync_approvals(self, request) -> None:
        existing = {r["id"] for r in self._query(
            "SELECT id FROM expense_approvals WHERE expense_request_id=?", (request.id,))}
        for approval in request.approvals:
            if approval.id in existing:
                continue
            self._insert("expense_approvals", {
                "id": approval.id, "expense_request_id": request.id,
                "approver_id": approval.approver_id, "decision": approval.decision,
                "reason": approval.reason, "decided_at": approval.decided_at,
            })

    def get(self, request_id: str):
        row = self._query_one("SELECT * FROM expense_requests WHERE id=?", (request_id,))
        return self._hydrate(row) if row else None

    def find_by_operation_id(self, operation_id: str):
        row = self._query_one("SELECT * FROM expense_requests WHERE operation_id=?",
                              (operation_id,))
        return self._hydrate(row) if row else None

    def find_by_payable(self, payable_id: str):
        row = self._query_one("SELECT * FROM expense_requests WHERE payable_id=?",
                              (payable_id,))
        return self._hydrate(row) if row else None

    def _hydrate(self, row: dict):
        from backend.domain.finance.entities.expense import ExpenseApproval, ExpenseRequest
        from backend.domain.finance.enums import ExpenseRequestStatus
        from backend.domain.finance.value_objects.money import Money
        currency = row["currency_code"]
        request = ExpenseRequest(
            id=row["id"], account_id=row["account_id"], period_code=row["period_code"],
            amount=Money.from_string(row["amount"], currency),
            requested_by=row["requested_by"], operation_id=row["operation_id"],
            budget_id=row["budget_id"], category=row["category"] or "",
            description=row["description"] or "", cost_center_id=row["cost_center_id"],
            project_id=row["project_id"], department_id=row["department_id"],
            branch_id=row["branch_id"], supplier_id=row["supplier_id"],
            status=ExpenseRequestStatus(row["status"]),
            required_approvals=int(row["required_approvals"]),
            excess_authorized=bool(row["excess_authorized"]),
            accrued_amount=Money.from_string(row["accrued_amount"], currency),
            settled_amount=Money.from_string(row["settled_amount"], currency),
            resolution_reason=row["resolution_reason"], payable_id=row["payable_id"],
            accrual_journal_entry_id=row["accrual_journal_entry_id"],
            document_reference=row["document_reference"],
            created_at=row["created_at"], updated_at=row["updated_at"])
        request.approvals = [
            ExpenseApproval(id=r["id"], expense_request_id=r["expense_request_id"],
                            approver_id=r["approver_id"], decision=r["decision"],
                            reason=r["reason"], decided_at=r["decided_at"])
            for r in self._query("SELECT * FROM expense_approvals WHERE expense_request_id=?"
                                 " ORDER BY decided_at", (row["id"],))]
        return request

    # ── reglas de aprobación ─────────────────────────────────────────────
    def save_rule(self, rule) -> None:
        self._insert("expense_approval_rules", {
            "id": rule.id, "name": rule.name, "min_amount": format(rule.min_amount, "f"),
            "branch_id": rule.branch_id, "category": rule.category,
            "cost_center_id": rule.cost_center_id, "requester_id": rule.requester_id,
            "required_approvals": rule.required_approvals, "priority": rule.priority,
            "active": int(rule.active), "created_at": rule.created_at,
            "updated_at": rule.updated_at,
        })

    def deactivate_rule(self, rule_id: str) -> None:
        self._update("expense_approval_rules", {"active": 0, "updated_at": _now()},
                     where="id=?", params=(rule_id,))

    def active_rules(self) -> list:
        from decimal import Decimal
        from backend.domain.finance.entities.expense import ExpenseApprovalRule
        return [ExpenseApprovalRule(
            id=r["id"], name=r["name"], min_amount=Decimal(str(r["min_amount"])),
            required_approvals=int(r["required_approvals"]), branch_id=r["branch_id"],
            category=r["category"], cost_center_id=r["cost_center_id"],
            requester_id=r["requester_id"], priority=int(r["priority"]),
            active=bool(r["active"]), created_at=r["created_at"], updated_at=r["updated_at"])
            for r in self._query("SELECT * FROM expense_approval_rules WHERE active=1")]


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
