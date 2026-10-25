"""Treasury repository — treasury accounts, their movements and bank statements."""

from __future__ import annotations

from datetime import date

from backend.domain.finance.entities.bank_statement import BankStatement, BankStatementLine
from backend.domain.finance.entities.treasury_account import TreasuryAccount
from backend.domain.finance.enums import StatementLineStatus, TreasuryAccountType
from backend.domain.finance.value_objects.money import Money
from backend.infrastructure.db.repositories.finance.base import FinanceRepositoryBase


def _account_to_entity(row: dict) -> TreasuryAccount:
    return TreasuryAccount(
        id=row["id"], name=row["name"],
        account_type=TreasuryAccountType(row["account_type"]),
        ledger_account_id=row["ledger_account_id"],
        currency_code=row["currency_code"], branch_id=row["branch_id"],
        bank_name=row["bank_name"], masked_account_number=row["masked_account_number"] or "",
        requires_reconciliation=bool(row["requires_reconciliation"]),
        restricted=bool(row["restricted"]), allows_overdraft=bool(row["allows_overdraft"]),
        active=bool(row["active"]),
        created_at=row["created_at"], updated_at=row["updated_at"],
    )


def _line_to_entity(row: dict) -> BankStatementLine:
    return BankStatementLine(
        id=row["id"], bank_statement_id=row["bank_statement_id"],
        transaction_date=date.fromisoformat(row["transaction_date"]),
        description=row["description"],
        amount=Money.from_string(row["amount"], row["currency_code"]),
        external_reference=row["external_reference"],
        matched_journal_line_id=row["matched_journal_line_id"],
        line_index=row["line_index"],
        status=StatementLineStatus(row["status"]),
        suggested_journal_line_id=row["suggested_journal_line_id"],
        suggestion_score=row["suggestion_score"],
        ignored_reason=row["ignored_reason"], ignored_by=row["ignored_by"],
        adjustment_journal_entry_id=row["adjustment_journal_entry_id"],
    )


def _line_mutable(line: BankStatementLine) -> dict:
    return {
        "status": line.status.value,
        "matched_journal_line_id": line.matched_journal_line_id,
        "suggested_journal_line_id": line.suggested_journal_line_id,
        "suggestion_score": line.suggestion_score,
        "ignored_reason": line.ignored_reason, "ignored_by": line.ignored_by,
        "adjustment_journal_entry_id": line.adjustment_journal_entry_id,
    }


class TreasuryRepository(FinanceRepositoryBase):
    # ── treasury accounts ────────────────────────────────────────────────
    def save(self, account: TreasuryAccount) -> None:
        self._insert("treasury_accounts", {
            "id": account.id, "name": account.name, "account_type": account.account_type.value,
            "ledger_account_id": account.ledger_account_id,
            "currency_code": account.currency_code, "branch_id": account.branch_id,
            "bank_name": account.bank_name,
            "masked_account_number": account.masked_account_number,
            "requires_reconciliation": int(account.requires_reconciliation),
            "restricted": int(account.restricted),
            "allows_overdraft": int(account.allows_overdraft), "active": int(account.active),
            "created_at": account.created_at, "updated_at": account.updated_at,
        })

    def update(self, account: TreasuryAccount) -> None:
        self._update("treasury_accounts", {
            "name": account.name, "bank_name": account.bank_name,
            "masked_account_number": account.masked_account_number,
            "requires_reconciliation": int(account.requires_reconciliation),
            "restricted": int(account.restricted),
            "allows_overdraft": int(account.allows_overdraft), "active": int(account.active),
            "updated_at": account.updated_at,
        }, where="id=?", params=(account.id,))

    def get(self, treasury_account_id: str) -> TreasuryAccount | None:
        row = self._query_one("SELECT * FROM treasury_accounts WHERE id=?",
                              (treasury_account_id,))
        return _account_to_entity(row) if row else None

    def list_active(self) -> list[TreasuryAccount]:
        return [_account_to_entity(r) for r in self._query(
            "SELECT * FROM treasury_accounts WHERE active=1 ORDER BY name")]

    def ledger_balance(self, ledger_account_id: str, currency_code: str) -> Money:
        """Saldo contable de la cuenta espejo: débitos − créditos contabilizados,
        sumados en Decimal (nunca una columna acumulada)."""
        from decimal import Decimal
        total = Decimal("0")
        for row in self._query(
                "SELECT jl.debit_amount, jl.credit_amount FROM journal_lines jl"
                " JOIN journal_entries je ON je.id = jl.journal_entry_id"
                " WHERE jl.account_id=? AND jl.currency_code=?"
                " AND je.status IN ('POSTED','REVERSED')", (ledger_account_id, currency_code)):
            total += Decimal(str(row["debit_amount"])) - Decimal(str(row["credit_amount"]))
        return Money(total, currency_code)

    # ── movimientos de tesorería (§13) ───────────────────────────────────
    def save_movement(self, values: dict) -> None:
        self._insert("treasury_movements", values)

    def find_movement_by_operation_id(self, operation_id: str) -> dict | None:
        return self._query_one("SELECT * FROM treasury_movements WHERE operation_id=?",
                               (operation_id,))

    # ── bank statements ──────────────────────────────────────────────────
    def save_statement(self, statement: BankStatement) -> None:
        self._insert("bank_statements", {
            "id": statement.id, "treasury_account_id": statement.treasury_account_id,
            "statement_date": statement.statement_date.isoformat(),
            "opening_balance": statement.opening_balance.to_string(),
            "closing_balance": statement.closing_balance.to_string(),
            "currency_code": statement.opening_balance.currency_code,
            "source_format": statement.source_format, "file_name": statement.file_name,
            "content_hash": statement.content_hash or statement.seal(),
            "imported_by": statement.imported_by, "operation_id": statement.operation_id,
            "imported_at": statement.imported_at,
        })
        for line in statement.lines:
            values = {
                "id": line.id, "bank_statement_id": line.bank_statement_id,
                "transaction_date": line.transaction_date.isoformat(),
                "description": line.description, "amount": line.amount.to_string(),
                "currency_code": line.amount.currency_code,
                "external_reference": line.external_reference,
                "line_index": line.line_index,
            }
            values.update(_line_mutable(line))
            self._insert("bank_statement_lines", values)

    def update_statement_line(self, line: BankStatementLine) -> None:
        self._update("bank_statement_lines", _line_mutable(line), where="id=?",
                     params=(line.id,))

    def get_statement(self, statement_id: str) -> BankStatement | None:
        row = self._query_one("SELECT * FROM bank_statements WHERE id=?", (statement_id,))
        return self._hydrate_statement(row) if row else None

    def find_statement_by_operation_id(self, operation_id: str) -> BankStatement | None:
        row = self._query_one("SELECT * FROM bank_statements WHERE operation_id=?",
                              (operation_id,))
        return self._hydrate_statement(row) if row else None

    def find_statement_by_hash(self, treasury_account_id: str,
                               content_hash: str) -> BankStatement | None:
        row = self._query_one(
            "SELECT * FROM bank_statements WHERE treasury_account_id=? AND content_hash=?",
            (treasury_account_id, content_hash))
        return self._hydrate_statement(row) if row else None

    def _hydrate_statement(self, row: dict) -> BankStatement:
        currency = row["currency_code"]
        statement = BankStatement(
            id=row["id"], treasury_account_id=row["treasury_account_id"],
            statement_date=date.fromisoformat(row["statement_date"]),
            opening_balance=Money.from_string(row["opening_balance"], currency),
            closing_balance=Money.from_string(row["closing_balance"], currency),
            operation_id=row["operation_id"], imported_at=row["imported_at"],
            source_format=row["source_format"], file_name=row["file_name"],
            content_hash=row["content_hash"], imported_by=row["imported_by"],
        )
        statement.lines.extend(_line_to_entity(r) for r in self._query(
            "SELECT * FROM bank_statement_lines WHERE bank_statement_id=? ORDER BY line_index",
            (row["id"],)))
        return statement
