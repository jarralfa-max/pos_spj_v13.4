"""RegisterReconciliationAdjustmentUseCase — ajuste AUTORIZADO desde la conciliación (§15).

Dos casos:

1. Partida del estado sin movimiento en el mayor (comisión, interés, depósito
   no identificado): se registra el movimiento de tesorería que faltaba y la
   partida queda conciliada contra su línea.
2. Partida conciliada con diferencia dentro de la tolerancia
   (ADJUSTMENT_REQUIRED): se contabiliza sólo la diferencia contra la cuenta
   de ajustes de conciliación y la partida queda MATCHED.

Segregación (§28): quien importó el estado no aprueba sus propios ajustes
(configurable). Permiso propio en la capa de comandos.
"""

from __future__ import annotations

from backend.application.services.finance.posting_engine import PostingEngine
from backend.application.use_cases.finance._support import require_profile
from backend.application.use_cases.finance.register_treasury_movement_use_case import (
    RegisterTreasuryMovementUseCase,
)
from backend.domain.finance.enums import (
    AuditAction,
    JournalType,
    PostingPurpose,
    StatementLineStatus,
    TreasuryMovementKind,
)
from backend.domain.finance.exceptions import ReconciliationError
from backend.domain.finance.policies.segregation_policy import SegregationPolicy
from backend.domain.finance.services.journal_posting_service import LineSpec
from backend.domain.finance.value_objects.money import Money
from backend.domain.finance.value_objects.posting_reference import PostingReference
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork


class RegisterReconciliationAdjustmentUseCase:
    def __init__(self) -> None:
        self._engine = PostingEngine()
        self._movement = RegisterTreasuryMovementUseCase()

    def execute(self, connection, *, reconciliation_id: str, bank_statement_line_id: str,
                operation_id: str, adjusted_by: str,
                kind: TreasuryMovementKind | None = None,
                counterpart_account_id: str | None = None, reason: str = "") -> str:
        with FinanceUnitOfWork(connection) as uow:
            reconciliation = uow.reconciliations.get(reconciliation_id)
            if reconciliation is None:
                raise ReconciliationError("La conciliación no existe")
            statement = uow.treasury.get_statement(reconciliation.bank_statement_id)
            account = uow.treasury.get(statement.treasury_account_id)
            line = statement.line(bank_statement_line_id)
            SegregationPolicy(uow.settings).enforce_statement_adjustment(
                imported_by=statement.imported_by, adjuster=adjusted_by)
            if line.status is StatementLineStatus.ADJUSTMENT_REQUIRED:
                entry_id = self._difference(uow, account, line, operation_id, adjusted_by,
                                            counterpart_account_id, reason)
                line.settle_adjustment(entry_id)
            elif line.is_open:
                if kind is None:
                    kind = (TreasuryMovementKind.DEPOSIT if line.amount.is_positive()
                            else TreasuryMovementKind.WITHDRAWAL)
                entry_id = self._movement.execute(
                    connection, treasury_account_id=account.id, kind=kind,
                    amount=line.amount.abs().to_string(), movement_date=line.transaction_date,
                    operation_id=operation_id, counterpart_account_id=counterpart_account_id,
                    reference=line.external_reference, description=line.description,
                    created_by=adjusted_by, bank_statement_line_id=line.id,
                    owns_transaction=False)
                entry = uow.journal_entries.get(entry_id)
                treasury_line = next(l for l in entry.lines
                                     if l.account_id == account.ledger_account_id)
                reconciliation.add_match(line.id, treasury_line.id, adjusted_by)
                line.mark_matched(treasury_line.id, exact=True)
                line.adjustment_journal_entry_id = entry_id
                uow.reconciliations.update(reconciliation)
            else:
                raise ReconciliationError(
                    f"La partida está {line.status.value}; no requiere ajuste")
            uow.treasury.update_statement_line(line)
            uow.audit(AuditAction.RECONCILED, entity_type="bank_statement_line",
                      entity_id=line.id, operation_id=operation_id, user_id=adjusted_by,
                      after={"status": line.status.value, "adjustment_journal_entry_id": entry_id},
                      reason=reason, branch_id=account.branch_id)
            return entry_id

    def _difference(self, uow: FinanceUnitOfWork, account, line, operation_id: str,
                    adjusted_by: str, counterpart_account_id: str | None, reason: str) -> str:
        ledger_row = uow.journal_entries.get_posted_line(line.matched_journal_line_id)
        currency = line.amount.currency_code
        ledger_signed = (Money.from_string(ledger_row["debit_amount"], currency)
                         .subtract(Money.from_string(ledger_row["credit_amount"], currency)))
        difference = line.amount.subtract(ledger_signed)
        if difference.is_zero():
            raise ReconciliationError("La partida no tiene diferencia que ajustar")
        counterpart = counterpart_account_id or require_profile(
            uow, "TREASURY", line.transaction_date, branch_id=account.branch_id
        ).account_for("reconciliation_adjustment_account_id")
        amount = difference.abs()
        inflow = difference.is_positive()
        entry = self._engine.post(
            uow, JournalType.BANK, line.transaction_date,
            f"Ajuste de conciliación {line.external_reference}".strip(),
            PostingReference("finance", line.id, PostingPurpose.RECONCILIATION_ADJUSTMENT,
                             operation_id),
            [LineSpec(account.ledger_account_id, debit=amount if inflow else None,
                      credit=None if inflow else amount,
                      description=reason or "Diferencia de conciliación",
                      source_reference=line.external_reference),
             LineSpec(counterpart, debit=None if inflow else amount,
                      credit=amount if inflow else None,
                      description=reason or "Diferencia de conciliación")],
            currency_code=currency, branch_id=account.branch_id, created_by=adjusted_by)
        return entry.id
