"""Bank reconciliation use case — match, confirm, and authorized undo.

Auditoría d9f2bca (F07/F08):
- sólo se concilia una línea contabilizada de la cuenta ESPEJO de la cuenta de
  tesorería del estado, en su moneda (antes una línea de CxC 1130 se
  conciliaba contra el banco 1110 sólo porque el importe coincidía);
- una línea del mayor o del estado con un match ACTIVO en cualquier
  conciliación no se reutiliza (antes la misma línea se concilió en dos
  estados distintos);
- completar exige todas las partidas del estado conciliadas, o un motivo de
  diferencia aceptada (quien llama exige el permiso para aceptarla);
- revertir inactiva los matches y libera las partidas, conservando historia.
"""

from __future__ import annotations

import json

from backend.domain.finance.entities.reconciliation import Reconciliation
from backend.domain.finance.enums import ReconciliationStatus
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
            treasury_account = uow.treasury.get(statement.treasury_account_id)
            if treasury_account is None:
                raise ReconciliationError("La cuenta de tesorería del estado no existe")
            if ledger_row["account_id"] != treasury_account.ledger_account_id:
                raise ReconciliationError(
                    "La línea contable no pertenece a la cuenta de tesorería del estado; "
                    "sólo se concilian movimientos de su cuenta espejo")
            currency = ledger_row["currency_code"]
            if currency != statement.opening_balance.currency_code:
                raise ReconciliationError(
                    f"La línea contable está en {currency} y el estado en "
                    f"{statement.opening_balance.currency_code}")
            if uow.reconciliations.journal_line_has_active_match(journal_line_id):
                raise ReconciliationError(
                    "La línea contable ya está conciliada en otra partida activa")
            if uow.reconciliations.statement_line_has_active_match(bank_statement_line_id):
                raise ReconciliationError("La partida del estado ya tiene un match activo")
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

    def complete(self, connection, *, reconciliation_id: str, completed_by: str,
                 difference_reason: str | None = None) -> None:
        with FinanceUnitOfWork(connection) as uow:
            reconciliation = uow.reconciliations.get(reconciliation_id)
            if reconciliation is None:
                raise FinanceDomainError("La conciliación no existe")
            statement = uow.treasury.get_statement(reconciliation.bank_statement_id)
            self._domain.complete(reconciliation, statement, completed_by,
                                  difference_reason=difference_reason)
            uow.reconciliations.update(reconciliation)

    def revert(self, connection, *, reconciliation_id: str, reverted_by: str, reason: str) -> None:
        with FinanceUnitOfWork(connection) as uow:
            reconciliation = uow.reconciliations.get(reconciliation_id)
            if reconciliation is None:
                raise FinanceDomainError("La conciliación no existe")
            if reconciliation.status is not ReconciliationStatus.COMPLETED:
                raise ReconciliationError("Sólo se revierte una conciliación completada")
            statement = uow.treasury.get_statement(reconciliation.bank_statement_id)
            for line in self._domain.revert(reconciliation, statement, reverted_by, reason):
                uow.treasury.update_statement_line(line)
            uow.reconciliations.update(reconciliation)

    def candidates(self, connection, *, reconciliation_id: str) -> dict:
        """Partidas del estado pendientes y líneas del mayor elegibles (de la
        cuenta espejo, contabilizadas, sin match activo) para la pantalla."""
        with FinanceUnitOfWork(connection) as uow:
            reconciliation = uow.reconciliations.get(reconciliation_id)
            if reconciliation is None:
                raise FinanceDomainError("La conciliación no existe")
            statement = uow.treasury.get_statement(reconciliation.bank_statement_id)
            account = uow.treasury.get(statement.treasury_account_id)
        from backend.application.queries.finance.general_ledger_query_service import (
            GeneralLedgerQueryService,
        )
        return {
            "statement_lines": [
                {"id": l.id, "transaction_date": l.transaction_date.isoformat(),
                 "description": l.description, "amount": l.amount.to_string(),
                 "external_reference": l.external_reference}
                for l in statement.lines if not l.reconciled
            ],
            "ledger_lines": GeneralLedgerQueryService(connection).unmatched_treasury_lines(
                account.ledger_account_id),
        }
