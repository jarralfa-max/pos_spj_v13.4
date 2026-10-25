"""RegisterTreasuryMovementUseCase — depósitos, retiros, cargos e intereses (§13).

Cada movimiento es UN documento (``treasury_movements`` + documento financiero)
y UN asiento balanceado contra una contrapartida explícita:

    Depósito:  Dr Tesorería / Cr contrapartida (p. ej. partidas por identificar)
    Retiro:    Dr contrapartida / Cr Tesorería           (exige saldo)
    Cargo:     Dr Comisiones bancarias / Cr Tesorería    (perfil TREASURY)
    Interés:   Dr Tesorería / Cr Intereses ganados        (perfil TREASURY)

Depósito y retiro exigen la contrapartida; nunca se adivina por texto libre.
"""

from __future__ import annotations

from datetime import date

from backend.application.services.finance.posting_engine import (
    PostingEngine,
    publish_finance_event,
)
from backend.application.use_cases.finance._support import (
    assert_available_funds,
    require_profile,
    require_treasury,
)
from backend.domain.finance.entities.financial_document import FinancialDocument
from backend.domain.finance.enums import (
    AuditAction,
    FinancialDocumentType,
    JournalType,
    PostingPurpose,
    TreasuryMovementKind,
)
from backend.domain.finance.exceptions import (
    AccountNotFoundError,
    FinanceDomainError,
    IdempotencyConflictError,
)
from backend.domain.finance.services.journal_posting_service import LineSpec
from backend.domain.finance.value_objects.money import Money
from backend.domain.finance.value_objects.posting_reference import PostingReference
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.events.event_names import EventName
from backend.shared.ids import new_uuid

_SPEC = {
    TreasuryMovementKind.DEPOSIT: (True, PostingPurpose.BANK_DEPOSIT,
                                   FinancialDocumentType.BANK_DEPOSIT, None),
    TreasuryMovementKind.WITHDRAWAL: (False, PostingPurpose.BANK_WITHDRAWAL,
                                      FinancialDocumentType.BANK_WITHDRAWAL, None),
    TreasuryMovementKind.BANK_CHARGE: (False, PostingPurpose.BANK_CHARGE,
                                       FinancialDocumentType.BANK_CHARGE,
                                       "bank_charge_account_id"),
    TreasuryMovementKind.BANK_INTEREST: (True, PostingPurpose.BANK_INTEREST,
                                         FinancialDocumentType.BANK_INTEREST,
                                         "bank_interest_account_id"),
}

_LABEL = {TreasuryMovementKind.DEPOSIT: "Depósito", TreasuryMovementKind.WITHDRAWAL: "Retiro",
          TreasuryMovementKind.BANK_CHARGE: "Cargo bancario",
          TreasuryMovementKind.BANK_INTEREST: "Interés bancario"}


class RegisterTreasuryMovementUseCase:
    def __init__(self) -> None:
        self._engine = PostingEngine()

    def execute(self, connection, *, treasury_account_id: str, kind: TreasuryMovementKind,
                amount: str, movement_date: date, operation_id: str,
                counterpart_account_id: str | None = None, reference: str = "",
                description: str = "", created_by: str | None = None,
                bank_statement_line_id: str | None = None,
                owns_transaction: bool = True) -> str:
        inflow, purpose, document_type, role = _SPEC[kind]
        with FinanceUnitOfWork(connection, owns_transaction=owns_transaction) as uow:
            previous = uow.treasury.find_movement_by_operation_id(operation_id)
            treasury = require_treasury(uow, treasury_account_id)
            money = Money.from_string(amount, treasury.currency_code)
            if previous is not None:
                if previous["kind"] != kind.value or Money.from_string(
                        previous["amount"], previous["currency_code"]).amount != money.amount:
                    raise IdempotencyConflictError(
                        f"La operación {operation_id} ya registró otro movimiento")
                return previous["journal_entry_id"]
            if not money.is_positive():
                raise FinanceDomainError("El movimiento debe ser mayor que cero")
            if role is not None:
                counterpart = require_profile(uow, "TREASURY", movement_date,
                                              branch_id=treasury.branch_id).account_for(role)
            else:
                if not counterpart_account_id:
                    raise FinanceDomainError(
                        f"Un {_LABEL[kind].lower()} indica su contrapartida contable")
                counterpart = counterpart_account_id
            account = uow.accounts.get(counterpart)
            if account is None:
                raise AccountNotFoundError("La cuenta de contrapartida no existe")
            if counterpart == treasury.ledger_account_id:
                raise FinanceDomainError(
                    "La contrapartida no puede ser la misma cuenta de tesorería; "
                    "use una transferencia entre cuentas")
            if not inflow:
                assert_available_funds(uow, treasury, money)
            document = FinancialDocument.create(
                document_type, reference or f"{kind.value[:3]}-{operation_id[-8:]}",
                movement_date, money, "finance", new_uuid(), new_uuid(),
                branch_id=treasury.branch_id)
            document.apply_settlement(money)
            uow.financial_documents.save(document)
            label = f"{_LABEL[kind]} {treasury.name} {reference}".strip()
            treasury_line = LineSpec(treasury.ledger_account_id,
                                     debit=money if inflow else None,
                                     credit=None if inflow else money,
                                     description=description or label,
                                     branch_id=treasury.branch_id, source_reference=reference)
            counter_line = LineSpec(counterpart, debit=None if inflow else money,
                                    credit=money if inflow else None,
                                    description=description or label,
                                    branch_id=treasury.branch_id)
            entry = self._engine.post(
                uow, JournalType.BANK, movement_date, label,
                PostingReference("finance", document.id, purpose, operation_id),
                [treasury_line, counter_line], currency_code=money.currency_code,
                branch_id=treasury.branch_id, created_by=created_by,
                source_document_type=document_type.value)
            movement_id = new_uuid()
            uow.treasury.save_movement({
                "id": movement_id, "treasury_account_id": treasury.id, "kind": kind.value,
                "amount": money.to_string(), "currency_code": money.currency_code,
                "movement_date": movement_date.isoformat(),
                "counterpart_account_id": counterpart, "reference": reference,
                "description": description, "financial_document_id": document.id,
                "journal_entry_id": entry.id, "bank_statement_line_id": bank_statement_line_id,
                "created_by": created_by, "branch_id": treasury.branch_id,
                "operation_id": operation_id, "created_at": document.created_at,
            })
            uow.audit(AuditAction.TREASURY_MOVEMENT, entity_type="treasury_movement",
                      entity_id=movement_id, operation_id=operation_id, user_id=created_by,
                      after={"kind": kind.value, "amount": money.to_string(),
                             "treasury_account_id": treasury.id,
                             "counterpart_account_id": counterpart,
                             "journal_entry_id": entry.id},
                      branch_id=treasury.branch_id)
            publish_finance_event(uow, EventName.TREASURY_MOVEMENT_REGISTERED, {
                "treasury_movement_id": movement_id, "kind": kind.value,
                "amount": money.to_string(), "treasury_account_id": treasury.id,
                "journal_entry_id": entry.id,
            }, operation_id=operation_id, entity_id=movement_id, branch_id=treasury.branch_id,
                source_document_id=document.id)
            return entry.id
