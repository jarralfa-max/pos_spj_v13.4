"""ReconciliationService — domain matching between statements and ledger lines."""

from __future__ import annotations

from dataclasses import dataclass

from backend.domain.finance.entities.bank_statement import BankStatement, BankStatementLine
from backend.domain.finance.entities.reconciliation import Reconciliation
from backend.domain.finance.exceptions import ReconciliationError
from backend.domain.finance.policies.reconciliation_policy import ReconciliationPolicy
from backend.domain.finance.value_objects.money import Money


@dataclass(frozen=True, slots=True)
class LedgerMovement:
    """Read-model of one postable ledger line eligible for matching."""

    journal_line_id: str
    amount: Money            # signed: positive inflow / negative outflow
    reference: str = ""


class ReconciliationDomainService:
    def __init__(self) -> None:
        self._policy = ReconciliationPolicy()

    def start(self, statement: BankStatement, operation_id: str) -> Reconciliation:
        self._policy.enforce_statement_consistency(statement)
        return Reconciliation.create(statement.treasury_account_id, statement.id, operation_id)

    def match(self, reconciliation: Reconciliation, statement_line: BankStatementLine,
              movement: LedgerMovement, matched_by: str) -> None:
        if statement_line.reconciled:
            raise ReconciliationError("La partida del estado ya está conciliada")
        self._policy.enforce_match_amount(statement_line, movement.amount)
        reconciliation.add_match(statement_line.id, movement.journal_line_id, matched_by)
        statement_line.matched_journal_line_id = movement.journal_line_id
        statement_line.reconciled = True

    def complete(self, reconciliation: Reconciliation, statement: BankStatement,
                 completed_by: str, *, difference_reason: str | None = None) -> None:
        unmatched = sum(1 for line in statement.lines if not line.reconciled)
        reconciliation.complete(completed_by, unmatched_lines=unmatched,
                                difference_reason=difference_reason)

    def revert(self, reconciliation: Reconciliation, statement: BankStatement,
               reverted_by: str, reason: str) -> list[BankStatementLine]:
        """Revierte y devuelve las partidas del estado que quedan libres."""
        released_ids = {m.bank_statement_line_id for m in reconciliation.active_matches()}
        reconciliation.revert(reverted_by, reason)
        released = []
        for line in statement.lines:
            if line.id in released_ids:
                line.reconciled = False
                line.matched_journal_line_id = None
                released.append(line)
        return released

    def suggest_matches(self, statement: BankStatement,
                        movements: list[LedgerMovement]) -> list[tuple[BankStatementLine, LedgerMovement]]:
        """Exact-amount suggestion; each side used at most once."""
        suggestions: list[tuple[BankStatementLine, LedgerMovement]] = []
        used: set[str] = set()
        for line in statement.lines:
            if line.reconciled:
                continue
            for movement in movements:
                if movement.journal_line_id in used:
                    continue
                if (movement.amount.currency_code == line.amount.currency_code
                        and movement.amount.amount == line.amount.amount):
                    suggestions.append((line, movement))
                    used.add(movement.journal_line_id)
                    break
        return suggestions
