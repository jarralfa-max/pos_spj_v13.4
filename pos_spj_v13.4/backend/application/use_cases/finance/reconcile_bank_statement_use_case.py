"""Bank reconciliation use case — sugerir, conciliar, ignorar, completar, deshacer (§15).

Auditoría d9f2bca (F07/F08) y FIN-ERP:
- sólo se concilia una línea CONTABILIZADA de la cuenta ESPEJO de la cuenta de
  tesorería del estado, en su moneda;
- una línea del mayor o del estado con un match ACTIVO en cualquier
  conciliación no se reutiliza (``TransactionAlreadyReconciledError``);
- el match es exacto o, dentro de la tolerancia configurada, deja la partida
  en ADJUSTMENT_REQUIRED hasta que un ajuste autorizado lo cierre;
- las sugerencias usan importe, fecha (ventana configurada) y referencia/folio;
- completar exige todas las partidas resueltas o un motivo de diferencia;
- deshacer exige permiso y motivo, libera las partidas y conserva la historia.
"""

from __future__ import annotations

from datetime import date

from backend.application.services.finance.posting_engine import publish_finance_event
from backend.domain.finance.entities.reconciliation import Reconciliation
from backend.domain.finance.enums import AuditAction, ReconciliationStatus
from backend.domain.finance.exceptions import (
    FinanceDomainError,
    ReconciliationError,
    TransactionAlreadyReconciledError,
)
from backend.domain.finance.services.reconciliation_service import (
    LedgerMovement,
    ReconciliationDomainService,
)
from backend.domain.finance.value_objects.money import Money
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.events.event_names import EventName
from backend.shared.ids import new_uuid


def _movement(row: dict) -> LedgerMovement:
    currency = row["currency_code"]
    signed = (Money.from_string(row["debit_amount"], currency)
              .subtract(Money.from_string(row["credit_amount"], currency)))
    reference = " ".join(filter(None, (row.get("source_reference"), row.get("entry_number"),
                                       row.get("description"), row.get("entry_description"))))
    return LedgerMovement(journal_line_id=row["journal_line_id"], amount=signed,
                          reference=reference,
                          movement_date=date.fromisoformat(str(row["posting_date"])[:10]))


class ReconcileBankStatementUseCase:
    def _domain(self, uow: FinanceUnitOfWork) -> ReconciliationDomainService:
        settings = uow.settings
        return ReconciliationDomainService(
            amount_tolerance=settings.reconciliation_amount_tolerance,
            date_window_days=settings.reconciliation_date_window_days)

    @staticmethod
    def _load(uow: FinanceUnitOfWork, reconciliation_id: str):
        reconciliation = uow.reconciliations.get(reconciliation_id)
        if reconciliation is None:
            raise FinanceDomainError("La conciliación no existe")
        statement = uow.treasury.get_statement(reconciliation.bank_statement_id)
        account = uow.treasury.get(statement.treasury_account_id)
        return reconciliation, statement, account

    def start(self, connection, *, bank_statement_id: str, operation_id: str,
              started_by: str | None = None) -> Reconciliation:
        with FinanceUnitOfWork(connection) as uow:
            duplicate = uow.reconciliations.find_by_operation_id(operation_id)
            if duplicate is not None:
                return duplicate
            statement = uow.treasury.get_statement(bank_statement_id)
            if statement is None:
                raise FinanceDomainError("El estado de cuenta no existe")
            reconciliation = self._domain(uow).start(statement, operation_id)
            uow.reconciliations.save(reconciliation)
            return reconciliation

    def suggest(self, connection, *, reconciliation_id: str) -> int:
        """Marca SUGGESTED las partidas con su mejor candidato; devuelve cuántas."""
        with FinanceUnitOfWork(connection) as uow:
            reconciliation, statement, account = self._load(uow, reconciliation_id)
            if reconciliation.status not in (ReconciliationStatus.OPEN,
                                             ReconciliationStatus.IN_PROGRESS):
                raise ReconciliationError("La conciliación ya no admite cambios")
            movements = [_movement(row) for row in uow.reconciliations.eligible_ledger_lines(
                account.ledger_account_id, account.currency_code)]
            suggestions = self._domain(uow).suggest_matches(statement, movements)
            for line, movement, score in suggestions:
                line.suggest(movement.journal_line_id, score)
                uow.treasury.update_statement_line(line)
            return len(suggestions)

    def match(self, connection, *, reconciliation_id: str, bank_statement_line_id: str,
              journal_line_id: str, matched_by: str) -> bool:
        """Devuelve ``True`` si el match fue exacto (``False`` = requiere ajuste)."""
        with FinanceUnitOfWork(connection) as uow:
            reconciliation, statement, account = self._load(uow, reconciliation_id)
            statement_line = statement.line(bank_statement_line_id)
            ledger_row = uow.journal_entries.get_posted_line(journal_line_id)
            if ledger_row is None:
                raise ReconciliationError("La línea contable no existe o no está contabilizada")
            if ledger_row["account_id"] != account.ledger_account_id:
                raise ReconciliationError(
                    "La línea contable no pertenece a la cuenta de tesorería del estado; "
                    "sólo se concilian movimientos de su cuenta espejo")
            if ledger_row["currency_code"] != statement.opening_balance.currency_code:
                raise ReconciliationError(
                    f"La línea contable está en {ledger_row['currency_code']} y el estado en "
                    f"{statement.opening_balance.currency_code}")
            if uow.reconciliations.journal_line_has_active_match(journal_line_id):
                raise TransactionAlreadyReconciledError(
                    "La línea contable ya está conciliada en otra partida activa")
            if uow.reconciliations.statement_line_has_active_match(bank_statement_line_id):
                raise TransactionAlreadyReconciledError(
                    "La partida del estado ya tiene un match activo")
            ledger_row = {**ledger_row, "journal_line_id": journal_line_id,
                          "source_reference": "", "entry_description": ""}
            exact = self._domain(uow).match(reconciliation, statement_line,
                                            _movement(ledger_row), matched_by)
            uow.reconciliations.update(reconciliation)
            uow.treasury.update_statement_line(statement_line)
            uow.audit(AuditAction.RECONCILED, entity_type="bank_statement_line",
                      entity_id=statement_line.id, operation_id=reconciliation.operation_id,
                      user_id=matched_by,
                      after={"journal_line_id": journal_line_id, "exact": exact,
                             "status": statement_line.status.value},
                      branch_id=account.branch_id)
            publish_finance_event(uow, EventName.BANK_TRANSACTION_RECONCILED, {
                "reconciliation_id": reconciliation.id,
                "bank_statement_line_id": bank_statement_line_id,
                "journal_line_id": journal_line_id, "exact": exact,
            }, operation_id=new_uuid(), entity_id=statement_line.id,
                branch_id=account.branch_id)
            return exact

    def ignore(self, connection, *, reconciliation_id: str, bank_statement_line_id: str,
               reason: str, ignored_by: str) -> None:
        with FinanceUnitOfWork(connection) as uow:
            reconciliation, statement, account = self._load(uow, reconciliation_id)
            if reconciliation.status not in (ReconciliationStatus.OPEN,
                                             ReconciliationStatus.IN_PROGRESS):
                raise ReconciliationError("La conciliación ya no admite cambios")
            line = statement.line(bank_statement_line_id)
            line.ignore(reason, ignored_by)
            uow.treasury.update_statement_line(line)
            uow.audit(AuditAction.RECONCILED, entity_type="bank_statement_line",
                      entity_id=line.id, operation_id=reconciliation.operation_id,
                      user_id=ignored_by, after={"status": line.status.value}, reason=reason,
                      branch_id=account.branch_id)

    def complete(self, connection, *, reconciliation_id: str, completed_by: str,
                 difference_reason: str | None = None) -> None:
        with FinanceUnitOfWork(connection) as uow:
            reconciliation, statement, account = self._load(uow, reconciliation_id)
            pending_adjustments = [l for l in statement.lines
                                   if l.status.value == "ADJUSTMENT_REQUIRED"]
            if pending_adjustments and not (difference_reason or "").strip():
                raise ReconciliationError(
                    f"{len(pending_adjustments)} partidas tienen diferencia pendiente de ajuste")
            self._domain(uow).complete(reconciliation, statement, completed_by,
                                       difference_reason=difference_reason)
            uow.reconciliations.update(reconciliation)
            uow.audit(AuditAction.RECONCILED, entity_type="reconciliation",
                      entity_id=reconciliation.id, operation_id=reconciliation.operation_id,
                      user_id=completed_by,
                      after={"status": reconciliation.status.value,
                             "difference_reason": reconciliation.difference_reason},
                      branch_id=account.branch_id)
            publish_finance_event(uow, EventName.BANK_RECONCILIATION_COMPLETED, {
                "reconciliation_id": reconciliation.id,
                "bank_statement_id": statement.id, "treasury_account_id": account.id,
                "difference_reason": reconciliation.difference_reason,
            }, operation_id=new_uuid(), entity_id=reconciliation.id,
                branch_id=account.branch_id)

    def revert(self, connection, *, reconciliation_id: str, reverted_by: str,
               reason: str) -> None:
        with FinanceUnitOfWork(connection) as uow:
            reconciliation, statement, account = self._load(uow, reconciliation_id)
            if reconciliation.status is not ReconciliationStatus.COMPLETED:
                raise ReconciliationError("Sólo se revierte una conciliación completada")
            for line in self._domain(uow).revert(reconciliation, statement, reverted_by, reason):
                uow.treasury.update_statement_line(line)
            uow.reconciliations.update(reconciliation)
            uow.audit(AuditAction.UNRECONCILED, entity_type="reconciliation",
                      entity_id=reconciliation.id, operation_id=new_uuid(),
                      user_id=reverted_by, before={"status": "COMPLETED"},
                      after={"status": reconciliation.status.value}, reason=reason,
                      branch_id=account.branch_id)

    def candidates(self, connection, *, reconciliation_id: str) -> dict:
        """Partidas del estado pendientes y líneas del mayor elegibles."""
        with FinanceUnitOfWork(connection) as uow:
            _, statement, account = self._load(uow, reconciliation_id)
            ledger = uow.reconciliations.eligible_ledger_lines(account.ledger_account_id,
                                                               account.currency_code)
        return {
            "statement_lines": [
                {"id": l.id, "transaction_date": l.transaction_date.isoformat(),
                 "description": l.description, "amount": l.amount.to_string(),
                 "external_reference": l.external_reference, "status": l.status.value,
                 "suggested_journal_line_id": l.suggested_journal_line_id,
                 "suggestion_score": l.suggestion_score}
                for l in statement.lines if not l.reconciled],
            "ledger_lines": ledger,
        }
