"""RegisterCapitalMovementUseCase — capital, retiros y préstamos (§17).

    Aportación:        Dr Tesorería / Cr Aportaciones de capital
    Retiro de socio:   Dr Retiros de socios / Cr Tesorería            (exige saldo)
    Préstamo recibido: Dr Tesorería / Cr Préstamos por pagar
    Abono a préstamo:  Dr Préstamos por pagar (principal)
                       Dr Intereses pagados (interés) / Cr Tesorería  (exige saldo)

Una aportación nunca es ingreso por ventas; un préstamo es pasivo. Cada
movimiento produce su documento, su asiento y su evento; idempotente.
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
from backend.domain.finance.entities.capital import CapitalTransaction, Loan
from backend.domain.finance.entities.financial_document import FinancialDocument
from backend.domain.finance.enums import (
    AuditAction,
    CapitalMovementKind,
    FinancialDocumentType,
    JournalType,
    PostingPurpose,
)
from backend.domain.finance.exceptions import FinanceDomainError, IdempotencyConflictError
from backend.domain.finance.services.journal_posting_service import LineSpec
from backend.domain.finance.value_objects.money import Money
from backend.domain.finance.value_objects.posting_reference import PostingReference
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.events.event_names import EventName
from backend.shared.ids import new_uuid

_KIND = {
    CapitalMovementKind.CONTRIBUTION: (FinancialDocumentType.CAPITAL_CONTRIBUTION,
                                       PostingPurpose.CAPITAL_CONTRIBUTION,
                                       EventName.CAPITAL_CONTRIBUTION_REGISTERED,
                                       "Aportación de capital"),
    CapitalMovementKind.WITHDRAWAL: (FinancialDocumentType.OWNER_WITHDRAWAL,
                                     PostingPurpose.OWNER_WITHDRAWAL,
                                     EventName.CAPITAL_WITHDRAWAL_REGISTERED,
                                     "Retiro de socio"),
    CapitalMovementKind.LOAN_RECEIVED: (FinancialDocumentType.LOAN, PostingPurpose.LOAN_RECEIVED,
                                        EventName.LOAN_RECEIVED, "Préstamo recibido"),
    CapitalMovementKind.LOAN_REPAYMENT: (FinancialDocumentType.LOAN_REPAYMENT,
                                         PostingPurpose.LOAN_REPAYMENT,
                                         EventName.LOAN_REPAYMENT_REGISTERED,
                                         "Abono a préstamo"),
}


class RegisterCapitalMovementUseCase:
    def __init__(self) -> None:
        self._engine = PostingEngine()

    def execute(self, connection, *, kind: CapitalMovementKind, amount: str,
                movement_date: date, treasury_account_id: str, operation_id: str,
                counterparty: str = "", interest_amount: str | None = None,
                loan_id: str | None = None, maturity_date: date | None = None,
                currency_code: str = "MXN", created_by: str | None = None) -> str:
        document_type, purpose, event, label = _KIND[kind]
        with FinanceUnitOfWork(connection) as uow:
            previous = uow.capital.find_transaction_by_operation_id(operation_id)
            if previous is not None:
                if previous.kind is not kind or previous.amount.amount != Money.from_string(
                        amount, previous.amount.currency_code).amount:
                    raise IdempotencyConflictError(
                        f"La operación {operation_id} ya registró otro movimiento de capital")
                return previous.journal_entry_id
            treasury = require_treasury(uow, treasury_account_id, currency_code=currency_code)
            money = Money.from_string(amount, treasury.currency_code)
            interest = Money.from_string(interest_amount or "0", treasury.currency_code)
            profile = require_profile(uow, "CAPITAL", movement_date)
            if kind is CapitalMovementKind.LOAN_RECEIVED:
                loan = Loan.create(counterparty, money, movement_date,
                                   profile.account_for("loan_payable_account_id"),
                                   f"{operation_id}:loan", maturity_date=maturity_date,
                                   created_by=created_by)
                uow.capital.save_loan(loan)
                loan_id = loan.id
            elif kind is CapitalMovementKind.LOAN_REPAYMENT:
                loan = uow.capital.get_loan(loan_id or "")
                if loan is None:
                    raise FinanceDomainError("El préstamo no existe")
                if money.is_positive():
                    loan.repay(money)
                    uow.capital.update_loan(loan)
            transaction = CapitalTransaction.create(
                kind, money, movement_date, treasury.id, operation_id,
                interest_amount=interest if interest.is_positive() else None,
                counterparty=counterparty, loan_id=loan_id, created_by=created_by,
                branch_id=treasury.branch_id)
            cash = transaction.cash_amount()
            if kind in (CapitalMovementKind.WITHDRAWAL, CapitalMovementKind.LOAN_REPAYMENT):
                assert_available_funds(uow, treasury, cash)
            document = FinancialDocument.create(
                document_type, f"{document_type.value[:3]}-{operation_id[-8:]}", movement_date,
                cash, "finance", transaction.id, new_uuid(), branch_id=treasury.branch_id)
            document.apply_settlement(cash)
            uow.financial_documents.save(document)
            lines = self._lines(kind, profile, treasury, money, interest, counterparty, label)
            entry = self._engine.post(
                uow, JournalType.GENERAL if kind in (CapitalMovementKind.CONTRIBUTION,
                                                     CapitalMovementKind.WITHDRAWAL)
                else JournalType.BANK, movement_date, f"{label} {counterparty}".strip(),
                PostingReference("finance", transaction.id, purpose, operation_id), lines,
                currency_code=money.currency_code, branch_id=treasury.branch_id,
                created_by=created_by, source_document_type=document_type.value)
            transaction.financial_document_id = document.id
            transaction.journal_entry_id = entry.id
            uow.capital.save_transaction(transaction)
            uow.audit(AuditAction.CAPITAL_MOVEMENT, entity_type="capital_transaction",
                      entity_id=transaction.id, operation_id=operation_id, user_id=created_by,
                      after={"kind": kind.value, "amount": money.to_string(),
                             "interest": interest.to_string(), "counterparty": counterparty,
                             "loan_id": loan_id, "journal_entry_id": entry.id},
                      branch_id=treasury.branch_id)
            publish_finance_event(uow, event, {
                "capital_transaction_id": transaction.id, "kind": kind.value,
                "amount": money.to_string(), "interest": interest.to_string(),
                "loan_id": loan_id, "journal_entry_id": entry.id,
            }, operation_id=operation_id, entity_id=transaction.id,
                branch_id=treasury.branch_id, source_document_id=document.id)
            return entry.id

    @staticmethod
    def _lines(kind, profile, treasury, money: Money, interest: Money, counterparty: str,
               label: str) -> list[LineSpec]:
        text = f"{label} {counterparty}".strip()
        if kind is CapitalMovementKind.CONTRIBUTION:
            return [LineSpec(treasury.ledger_account_id, debit=money, description=text),
                    LineSpec(profile.account_for("capital_account_id"), credit=money,
                             description=text)]
        if kind is CapitalMovementKind.WITHDRAWAL:
            return [LineSpec(profile.account_for("owner_withdrawal_account_id"), debit=money,
                             description=text),
                    LineSpec(treasury.ledger_account_id, credit=money, description=text)]
        if kind is CapitalMovementKind.LOAN_RECEIVED:
            return [LineSpec(treasury.ledger_account_id, debit=money, description=text),
                    LineSpec(profile.account_for("loan_payable_account_id"), credit=money,
                             description=text)]
        lines = []
        if money.is_positive():
            lines.append(LineSpec(profile.account_for("loan_payable_account_id"), debit=money,
                                  description=f"{text} (principal)"))
        if interest.is_positive():
            lines.append(LineSpec(profile.account_for("loan_interest_account_id"),
                                  debit=interest, description=f"{text} (intereses)"))
        lines.append(LineSpec(treasury.ledger_account_id, credit=money.add(interest),
                              description=text))
        return lines
