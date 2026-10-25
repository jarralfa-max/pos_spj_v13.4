"""Anticipos a proveedor (§12).

- Registrar: sale dinero antes del documento.  Dr Anticipos a proveedores / Cr Tesorería
- Aplicar:   la factura llega y el anticipo la paga.  Dr Proveedores / Cr Anticipos
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from backend.application.finance.ports import SupplierDirectoryPort
from backend.application.services.finance.posting_engine import (
    PostingEngine,
    publish_finance_event,
)
from backend.application.use_cases.finance._support import (
    FORBIDDEN_SUPPLIER_PAYMENT_SOURCES,
    assert_available_funds,
    require_profile,
    require_treasury,
)
from backend.domain.finance.entities.payable import SupplierAdvance
from backend.domain.finance.enums import AuditAction, JournalType, PostingPurpose
from backend.domain.finance.exceptions import (
    FinanceDomainError,
    IdempotencyConflictError,
    PayableNotFoundError,
    PaymentAuthorizationError,
)
from backend.domain.finance.services.journal_posting_service import LineSpec
from backend.domain.finance.services.payable_service import PayableService
from backend.domain.finance.value_objects.money import Money
from backend.domain.finance.value_objects.posting_reference import PostingReference
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.events.event_names import EventName
from backend.shared.ids import new_uuid


class RegisterSupplierAdvanceUseCase:
    def __init__(self, supplier_directory: SupplierDirectoryPort) -> None:
        self._engine = PostingEngine()
        self._directory = supplier_directory

    def execute(self, connection, *, supplier_id: str, amount: str, treasury_account_id: str,
                advance_date: date, execution_reference: str, operation_id: str,
                created_by: str, branch_id: str | None = None) -> SupplierAdvance:
        if not (execution_reference or "").strip():
            raise PaymentAuthorizationError("Registre la evidencia del anticipo (folio, cheque)")
        with FinanceUnitOfWork(connection) as uow:
            duplicate = uow.supplier_payments.find_advance_by_operation_id(operation_id)
            if duplicate is not None:
                if duplicate.supplier_id != supplier_id:
                    raise IdempotencyConflictError(
                        f"La operación {operation_id} ya registró otro anticipo")
                return duplicate
            treasury = require_treasury(uow, treasury_account_id, money_only=False)
            forbidden = FORBIDDEN_SUPPLIER_PAYMENT_SOURCES.get(treasury.account_type)
            if forbidden:
                raise FinanceDomainError(forbidden)
            eligibility = self._directory.payment_eligibility(supplier_id)
            if not eligibility.eligible:
                raise PaymentAuthorizationError(eligibility.reason)
            money = Money.from_string(amount, treasury.currency_code)
            assert_available_funds(uow, treasury, money)
            advance = SupplierAdvance.create(supplier_id, money, advance_date, treasury.id,
                                             operation_id, reference=execution_reference,
                                             branch_id=branch_id, created_by=created_by)
            profile = require_profile(uow, "PURCHASE", advance_date, branch_id=branch_id)
            entry = self._engine.post(
                uow, JournalType.BANK, advance_date,
                f"Anticipo a proveedor {eligibility.name}".strip(),
                PostingReference("finance", advance.id, PostingPurpose.SUPPLIER_ADVANCE,
                                 operation_id),
                [LineSpec(profile.account_for("supplier_advance_account_id"), debit=money,
                          description="Anticipo entregado", supplier_id=supplier_id),
                 LineSpec(treasury.ledger_account_id, credit=money,
                          description=f"Salida por anticipo ({execution_reference.strip()})",
                          supplier_id=supplier_id,
                          source_reference=execution_reference.strip())],
                currency_code=money.currency_code, branch_id=branch_id, created_by=created_by)
            advance.journal_entry_id = entry.id
            uow.supplier_payments.save_advance(advance)
            uow.audit(AuditAction.PAYMENT_EXECUTED, entity_type="supplier_advance",
                      entity_id=advance.id, operation_id=operation_id, user_id=created_by,
                      after={"supplier_id": supplier_id, "amount": money.to_string(),
                             "journal_entry_id": entry.id}, branch_id=branch_id)
            publish_finance_event(uow, EventName.SUPPLIER_ADVANCE_REGISTERED, {
                "supplier_advance_id": advance.id, "supplier_id": supplier_id,
                "amount": money.to_string(), "journal_entry_id": entry.id,
            }, operation_id=operation_id, entity_id=advance.id, branch_id=branch_id)
            return advance


class ApplySupplierAdvanceUseCase:
    def __init__(self) -> None:
        self._engine = PostingEngine()

    def execute(self, connection, *, supplier_advance_id: str, payable_id: str, amount: str,
                application_date: date, operation_id: str, applied_by: str) -> str:
        with FinanceUnitOfWork(connection) as uow:
            previous = uow.supplier_payments.find_advance_application(operation_id)
            if previous is not None:
                return previous["journal_entry_id"]
            advance = uow.supplier_payments.get_advance(supplier_advance_id)
            if advance is None:
                raise FinanceDomainError("El anticipo no existe")
            payable = uow.payables.get(payable_id)
            if payable is None:
                raise PayableNotFoundError("La cuenta por pagar no existe")
            money = Money.from_string(amount, advance.amount.currency_code)
            PayableService.apply_advance(advance, payable, money, application_date)
            profile = require_profile(uow, "PURCHASE", application_date,
                                      branch_id=payable.branch_id)
            entry = self._engine.post(
                uow, JournalType.PURCHASES, application_date, "Aplicación de anticipo a proveedor",
                PostingReference("finance", new_uuid(), PostingPurpose.SUPPLIER_ADVANCE_APPLICATION,
                                 operation_id),
                [LineSpec(profile.account_for("payable_account_id"), debit=money,
                          description="CxP pagada con anticipo", supplier_id=payable.supplier_id),
                 LineSpec(profile.account_for("supplier_advance_account_id"), credit=money,
                          description="Anticipo aplicado", supplier_id=payable.supplier_id)],
                currency_code=money.currency_code, branch_id=payable.branch_id,
                created_by=applied_by)
            uow.supplier_payments.update_advance(advance)
            uow.payables.update(payable)
            document = uow.financial_documents.get(payable.financial_document_id)
            if document is not None:
                document.apply_settlement(money)
                uow.financial_documents.update(document)
            uow.supplier_payments.save_advance_application(
                application_id=new_uuid(), advance_id=advance.id, payable_id=payable.id,
                amount=money, journal_entry_id=entry.id, created_by=applied_by,
                operation_id=operation_id,
                created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
            uow.audit(AuditAction.PAYMENT_EXECUTED, entity_type="supplier_advance",
                      entity_id=advance.id, operation_id=operation_id, user_id=applied_by,
                      after={"payable_id": payable.id, "applied": money.to_string(),
                             "available": advance.available().to_string()},
                      branch_id=payable.branch_id)
            if payable.outstanding_amount.is_zero():
                publish_finance_event(uow, EventName.PAYABLE_SETTLED, {
                    "payable_id": payable.id, "supplier_id": payable.supplier_id,
                }, operation_id=operation_id, entity_id=payable.id, branch_id=payable.branch_id)
            return entry.id
