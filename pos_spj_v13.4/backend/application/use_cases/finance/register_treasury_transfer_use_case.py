"""RegisterTreasuryTransferUseCase — UN documento y UN asiento balanceado (§13).

    Transferencia Banco A → Banco B:   Dr Banco B / Cr Banco A

Nunca un ingreso y un egreso independientes. La cuenta origen debe tener saldo
(salvo sobregiro pactado) y no ser de fondos restringidos; un monedero
promocional no es dinero (F14).
"""

from __future__ import annotations

from datetime import date

from backend.application.services.finance.posting_engine import (
    PostingEngine,
    publish_finance_event,
)
from backend.application.use_cases.finance._support import (
    assert_available_funds,
    require_treasury,
)
from backend.domain.finance.entities.financial_document import FinancialDocument
from backend.domain.finance.enums import (
    AuditAction,
    FinancialDocumentType,
    JournalType,
    PostingPurpose,
)
from backend.domain.finance.exceptions import DuplicateTreasuryTransferError
from backend.domain.finance.services.journal_posting_service import LineSpec
from backend.domain.finance.services.treasury_service import TreasuryService
from backend.domain.finance.value_objects.money import Money
from backend.domain.finance.value_objects.posting_reference import PostingReference
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.events.event_names import EventName
from backend.shared.ids import new_uuid


class RegisterTreasuryTransferUseCase:
    def __init__(self) -> None:
        self._engine = PostingEngine()
        self._domain = TreasuryService()

    def execute(self, connection, *, source_treasury_account_id: str,
                target_treasury_account_id: str, amount: str, transfer_date: date,
                reference: str = "", operation_id: str, created_by: str | None = None) -> str:
        with FinanceUnitOfWork(connection) as uow:
            duplicate = uow.journal_entries.find_by_operation_id(operation_id)
            source = require_treasury(uow, source_treasury_account_id)
            target = require_treasury(uow, target_treasury_account_id)
            money = Money.from_string(amount, source.currency_code)
            if duplicate is not None:
                amounts = {line.account_id: line for line in duplicate.lines}
                same = (duplicate.posting_reference.posting_purpose
                        is PostingPurpose.TREASURY_TRANSFER
                        and target.ledger_account_id in amounts
                        and amounts[target.ledger_account_id].debit.amount == money.amount)
                if not same:
                    raise DuplicateTreasuryTransferError(
                        f"La operación {operation_id} ya registró otra transferencia")
                return duplicate.id
            self._domain.validate_transfer(source, target, money)
            assert_available_funds(uow, source, money)
            document = FinancialDocument.create(
                FinancialDocumentType.TREASURY_TRANSFER, reference or f"TRF-{operation_id[-8:]}",
                transfer_date, money, "finance", new_uuid(), new_uuid())
            document.apply_settlement(money)  # una transferencia se liquida al registrarse
            uow.financial_documents.save(document)
            entry = self._engine.post(
                uow, JournalType.BANK, transfer_date,
                f"Transferencia {source.name} → {target.name}",
                PostingReference("finance", document.id, PostingPurpose.TREASURY_TRANSFER,
                                 operation_id),
                [
                    LineSpec(target.ledger_account_id, debit=money,
                             description=f"Entrada por transferencia {reference}".strip(),
                             branch_id=target.branch_id, source_reference=reference),
                    LineSpec(source.ledger_account_id, credit=money,
                             description=f"Salida por transferencia {reference}".strip(),
                             branch_id=source.branch_id, source_reference=reference),
                ],
                currency_code=money.currency_code, created_by=created_by,
                source_document_type=FinancialDocumentType.TREASURY_TRANSFER.value)
            uow.audit(AuditAction.TREASURY_MOVEMENT, entity_type="treasury_transfer",
                      entity_id=document.id, operation_id=operation_id, user_id=created_by,
                      after={"source": source.id, "target": target.id,
                             "amount": money.to_string(), "journal_entry_id": entry.id,
                             "reference": reference})
            publish_finance_event(uow, EventName.TREASURY_TRANSFER_REGISTERED, {
                "transfer_id": document.id, "journal_entry_id": entry.id,
                "amount": money.to_string(), "source": source.id, "target": target.id,
            }, operation_id=operation_id, entity_id=document.id)
            return entry.id
