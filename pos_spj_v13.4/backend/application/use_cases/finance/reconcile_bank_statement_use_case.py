"""Bank reconciliation use case — match, confirm, and authorized undo."""

from __future__ import annotations

import json

from backend.domain.finance.entities.reconciliation import Reconciliation
from backend.domain.finance.exceptions import FinanceDomainError, ReconciliationError
from backend.domain.finance.services.reconciliation_service import (
    LedgerMovement,
    ReconciliationDomainService,
)
from backend.domain.finance.value_objects.money import Money
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.events.event_names import EventName
from backend.shared.ids import new_uuid


class ReconcileBankStatementUseCase:
    """Creates the reconciliation for an imported statement, applies matches and
    completes it. Undo requires user + reason (audited)."""

    def __init__(self) -> None:
        self._domain = ReconciliationDomainService()

    def start(self, connection, *, bank_statement_id: str, operation_id: str) -> Reconciliation:
        with FinanceUnitOfWork(connection) as uow:
            duplicate = uow.reconciliations.find_by_operation_id(operation_id)
            if duplicate is not None:
                return duplicate
            statement = uow.treasury.get_statement(bank_statement_id)
            if statement is None:
                raise FinanceDomainError("El estado de cuenta no existe")
            reconciliation = self._domain.start(statement, operation_id)
            uow.reconciliations.save(reconciliation)
            return reconciliation

    def match(self, connection, *, reconciliation_id: str, bank_statement_line_id: str,
              journal_line_id: str, matched_by: str) -> None:
        with FinanceUnitOfWork(connection) as uow:
            reconciliation = uow.reconciliations.get(reconciliation_id)
            if reconciliation is None:
                raise FinanceDomainError("La conciliación no existe")
            statement = uow.treasury.get_statement(reconciliation.bank_statement_id)
            statement_line = next(
                (l for l in statement.lines if l.id == bank_statement_line_id), None,
            )
            if statement_line is None:
                raise FinanceDomainError("La línea del estado de cuenta no existe")
            ledger_row = uow.journal_entries.get_posted_line(journal_line_id)
            if ledger_row is None:
                raise ReconciliationError("La línea contable no existe o no está contabilizada")
            currency = ledger_row["currency_code"]
            signed = (Money.from_string(ledger_row["debit_amount"], currency)
                      .subtract(Money.from_string(ledger_row["credit_amount"], currency)))
            movement = LedgerMovement(journal_line_id=journal_line_id, amount=signed)
            self._domain.match(reconciliation, statement_line, movement, matched_by)
            uow.reconciliations.update(reconciliation)
            uow.treasury.update_statement_line(statement_line)
            uow.outbox.enqueue(
                event_id=new_uuid(),
                event_name=EventName.BANK_TRANSACTION_RECONCILED.value,
                payload_json=json.dumps({
                    "reconciliation_id": reconciliation.id,
                    "bank_statement_line_id": bank_statement_line_id,
                    "journal_line_id": journal_line_id,
                }),
                operation_id=new_uuid(),
            )

    def complete(self, connection, *, reconciliation_id: str, completed_by: str) -> None:
        with FinanceUnitOfWork(connection) as uow:
            reconciliation = uow.reconciliations.get(reconciliation_id)
            if reconciliation is None:
                raise FinanceDomainError("La conciliación no existe")
            reconciliation.complete(completed_by)
            uow.reconciliations.update(reconciliation)

    def revert(self, connection, *, reconciliation_id: str, reverted_by: str, reason: str) -> None:
        with FinanceUnitOfWork(connection) as uow:
            reconciliation = uow.reconciliations.get(reconciliation_id)
            if reconciliation is None:
                raise FinanceDomainError("La conciliación no existe")
            reconciliation.revert(reverted_by, reason)
            uow.reconciliations.update(reconciliation)
