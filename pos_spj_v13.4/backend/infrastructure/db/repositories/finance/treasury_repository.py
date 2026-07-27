"""Treasury repository — treasury accounts and imported bank statements."""

from __future__ import annotations

from datetime import date

from backend.domain.finance.entities.bank_statement import BankStatement, BankStatementLine
from backend.domain.finance.entities.treasury_account import TreasuryAccount
from backend.domain.finance.enums import TreasuryAccountType
from backend.domain.finance.value_objects.money import Money
from backend.infrastructure.db.repositories.finance.base import FinanceRepositoryBase

_ACCOUNT_COLUMNS = ("id, name, account_type, ledger_account_id, currency_code, branch_id,"
                    " bank_name, bank_account_number, requires_reconciliation, active,"
                    " created_at, updated_at")
_STATEMENT_COLUMNS = ("id, treasury_account_id, statement_date, opening_balance,"
                      " closing_balance, currency_code, operation_id, imported_at")
_LINE_COLUMNS = ("id, bank_statement_id, transaction_date, description, amount,"
                 " currency_code, external_reference, matched_journal_line_id,"
                 " reconciled, line_index")


def _account_to_entity(row: dict) -> TreasuryAccount:
    return TreasuryAccount(
        id=row["id"], name=row["name"],
        account_type=TreasuryAccountType(row["account_type"]),
        ledger_account_id=row["ledger_account_id"],
        currency_code=row["currency_code"], branch_id=row["branch_id"],
        bank_name=row["bank_name"], bank_account_number=row["bank_account_number"],
        requires_reconciliation=bool(row["requires_reconciliation"]),
        active=bool(row["active"]),
        created_at=row["created_at"], updated_at=row["updated_at"],
    )


class TreasuryRepository(FinanceRepositoryBase):
    # ── treasury accounts ────────────────────────────────────────────────
    def save(self, account: TreasuryAccount) -> None:
        self._execute(
            f"INSERT INTO treasury_accounts ({_ACCOUNT_COLUMNS})"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (account.id, account.name, account.account_type.value,
             account.ledger_account_id, account.currency_code, account.branch_id,
             account.bank_name, account.bank_account_number,
             int(account.requires_reconciliation), int(account.active),
             account.created_at, account.updated_at),
        )

    def update(self, account: TreasuryAccount) -> None:
        self._execute(
            "UPDATE treasury_accounts SET name=?, requires_reconciliation=?, active=?,"
            " updated_at=? WHERE id=?",
            (account.name, int(account.requires_reconciliation), int(account.active),
             account.updated_at, account.id),
        )

    def get(self, treasury_account_id: str) -> TreasuryAccount | None:
        row = self._query_one(
            f"SELECT {_ACCOUNT_COLUMNS} FROM treasury_accounts WHERE id=?",
            (treasury_account_id,),
        )
        return _account_to_entity(row) if row else None

    def list_active(self) -> list[TreasuryAccount]:
        rows = self._query(
            f"SELECT {_ACCOUNT_COLUMNS} FROM treasury_accounts WHERE active=1 ORDER BY name"
        )
        return [_account_to_entity(row) for row in rows]

    # ── bank statements ──────────────────────────────────────────────────
    def save_statement(self, statement: BankStatement) -> None:
        self._execute(
            f"INSERT INTO bank_statements ({_STATEMENT_COLUMNS}) VALUES (?,?,?,?,?,?,?,?)",
            (statement.id, statement.treasury_account_id,
             statement.statement_date.isoformat(),
             statement.opening_balance.to_string(), statement.closing_balance.to_string(),
             statement.opening_balance.currency_code, statement.operation_id,
             statement.imported_at),
        )
        for line in statement.lines:
            self._execute(
                f"INSERT INTO bank_statement_lines ({_LINE_COLUMNS})"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (line.id, line.bank_statement_id, line.transaction_date.isoformat(),
                 line.description, line.amount.to_string(), line.amount.currency_code,
                 line.external_reference, line.matched_journal_line_id,
                 int(line.reconciled), line.line_index),
            )

    def update_statement_line(self, line: BankStatementLine) -> None:
        self._execute(
            "UPDATE bank_statement_lines SET matched_journal_line_id=?, reconciled=? WHERE id=?",
            (line.matched_journal_line_id, int(line.reconciled), line.id),
        )

    def get_statement(self, statement_id: str) -> BankStatement | None:
        row = self._query_one(
            f"SELECT {_STATEMENT_COLUMNS} FROM bank_statements WHERE id=?", (statement_id,)
        )
        return self._hydrate_statement(row) if row else None

    def find_statement_by_operation_id(self, operation_id: str) -> BankStatement | None:
        row = self._query_one(
            f"SELECT {_STATEMENT_COLUMNS} FROM bank_statements WHERE operation_id=?",
            (operation_id,),
        )
        return self._hydrate_statement(row) if row else None

    def _hydrate_statement(self, row: dict) -> BankStatement:
        currency = row["currency_code"]
        statement = BankStatement(
            id=row["id"], treasury_account_id=row["treasury_account_id"],
            statement_date=date.fromisoformat(row["statement_date"]),
            opening_balance=Money.from_string(row["opening_balance"], currency),
            closing_balance=Money.from_string(row["closing_balance"], currency),
            operation_id=row["operation_id"], imported_at=row["imported_at"],
        )
        for line_row in self._query(
            f"SELECT {_LINE_COLUMNS} FROM bank_statement_lines"
            " WHERE bank_statement_id=? ORDER BY line_index",
            (row["id"],),
        ):
            statement.lines.append(BankStatementLine(
                id=line_row["id"], bank_statement_id=line_row["bank_statement_id"],
                transaction_date=date.fromisoformat(line_row["transaction_date"]),
                description=line_row["description"],
                amount=Money.from_string(line_row["amount"], line_row["currency_code"]),
                external_reference=line_row["external_reference"],
                matched_journal_line_id=line_row["matched_journal_line_id"],
                reconciled=bool(line_row["reconciled"]),
                line_index=line_row["line_index"],
            ))
        return statement
