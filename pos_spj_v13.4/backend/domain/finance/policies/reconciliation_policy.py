"""Reconciliation policy — matching rules between statements and ledger lines."""

from __future__ import annotations

from backend.domain.finance.entities.bank_statement import BankStatement, BankStatementLine
from backend.domain.finance.exceptions import ReconciliationError
from backend.domain.finance.value_objects.money import Money


class ReconciliationPolicy:
    def enforce_statement_consistency(self, statement: BankStatement) -> None:
        if not statement.is_internally_consistent():
            raise ReconciliationError(
                f"Statement {statement.id} is inconsistent: opening "
                f"{statement.opening_balance.to_string()} + movements "
                f"{statement.movement_total().to_string()} != closing "
                f"{statement.closing_balance.to_string()}"
            )

    def enforce_match_amount(self, statement_line: BankStatementLine, ledger_amount: Money) -> None:
        """A match is exact by amount; differences require an explicit adjustment entry."""
        if statement_line.amount.currency_code != ledger_amount.currency_code:
            raise ReconciliationError("Cannot match lines in different currencies")
        if statement_line.amount.amount != ledger_amount.amount:
            raise ReconciliationError(
                f"Match amounts differ: statement {statement_line.amount.to_string()} "
                f"vs ledger {ledger_amount.to_string()}; register an adjustment entry instead"
            )
