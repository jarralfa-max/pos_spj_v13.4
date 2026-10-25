"""CreatePayableUseCase — obligación con proveedor y su documento fuente (§12).

- F01: la CxP y su asiento se escriben en UNA transacción (``create_payable_in``
  dentro de la unidad de trabajo de quien llama).
- F11: una CxP creada desde Finanzas declara su contrapartida (gasto,
  inventario, activo) y nace con asiento; Compras la reconoce en su propio asiento.
- Retención configurable: el documento es por el total; la obligación con el
  proveedor es el neto y la retención va a su cuenta por enterar.
- Validación de tres vías: si la recepción difiere de la orden/factura, la
  obligación nace BLOQUEADA y no se paga sin desbloqueo autorizado.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from backend.application.services.finance.posting_engine import (
    PostingEngine,
    publish_finance_event,
)
from backend.application.use_cases.finance._support import require_profile
from backend.domain.finance.entities.financial_document import FinancialDocument
from backend.domain.finance.entities.payable import Payable
from backend.domain.finance.enums import (
    AuditAction,
    FinancialDocumentType,
    JournalType,
    PaymentPriority,
    PostingPurpose,
    PurchaseDebitNature,
)
from backend.domain.finance.exceptions import FinanceDomainError, IdempotencyConflictError
from backend.domain.finance.services.journal_posting_service import LineSpec
from backend.domain.finance.value_objects.money import Money
from backend.domain.finance.value_objects.posting_reference import PostingReference
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.events.event_names import EventName
from backend.shared.ids import new_uuid

#: Orígenes que reconocen la obligación en su propio asiento (el puente de Compras).
SELF_RECOGNIZING_SOURCES = frozenset({"procurement"})

#: Rol contable del débito según la naturaleza configurada (§21).
NATURE_ROLE = {
    PurchaseDebitNature.INVENTORY: "inventory_account_id",
    PurchaseDebitNature.OPERATING_EXPENSE: "expense_account_id",
    PurchaseDebitNature.FIXED_ASSET: "asset_account_id",
}


def create_payable_in(uow: FinanceUnitOfWork, *, supplier_id: str, amount: str,
                      currency_code: str, document_number: str, issue_date: date,
                      due_date: date | None, branch_id: str | None, source_module: str,
                      source_document_id: str | None, operation_id: str,
                      retention_amount: str | None = None,
                      priority: PaymentPriority = PaymentPriority.NORMAL,
                      payment_terms: str = "",
                      debit_nature: PurchaseDebitNature = PurchaseDebitNature.INVENTORY,
                      purchase_order_id: str | None = None,
                      goods_receipt_id: str | None = None,
                      receipt_difference: str | None = None,
                      early_payment_discount_percent: Decimal | str | None = None,
                      early_payment_discount_until: date | None = None) -> Payable:
    """Crea documento + CxP dentro de una unidad de trabajo YA abierta."""
    gross = Money.from_string(amount, currency_code)
    retention = Money.from_string(retention_amount or "0", currency_code)
    existing = uow.payables.find_by_operation_id(operation_id)
    if existing is not None:
        if (existing.supplier_id != supplier_id
                or existing.original_amount.currency_code != gross.currency_code
                or existing.original_amount.add(existing.retention_amount).amount
                != gross.amount):
            raise IdempotencyConflictError(
                f"La operación {operation_id} ya creó una CxP por "
                f"{existing.original_amount.to_string()} con otro contenido")
        return existing
    if retention.is_negative() or retention >= gross:
        raise FinanceDomainError("La retención va de cero a menos que el total del documento")
    document = FinancialDocument.create(
        FinancialDocumentType.SUPPLIER_INVOICE, document_number, issue_date, gross,
        source_module, source_document_id or new_uuid(), new_uuid(),
        branch_id=branch_id, supplier_id=supplier_id, due_date=due_date,
    )
    uow.financial_documents.save(document)
    payable = Payable.create(
        supplier_id, document.id, gross.subtract(retention), issue_date, operation_id,
        due_date=due_date, branch_id=branch_id, priority=priority,
        payment_terms=payment_terms, debit_nature=debit_nature,
        purchase_order_id=purchase_order_id, goods_receipt_id=goods_receipt_id,
        retention_amount=retention,
        early_payment_discount_percent=(Decimal(str(early_payment_discount_percent))
                                        if early_payment_discount_percent not in (None, "")
                                        else None),
        early_payment_discount_until=early_payment_discount_until,
    )
    if (receipt_difference or "").strip():
        payable.block(f"Diferencia de recepción: {receipt_difference.strip()}")
    uow.payables.save(payable)
    publish_finance_event(uow, EventName.PAYABLE_CREATED, {
        "payable_id": payable.id, "supplier_id": supplier_id,
        "amount": payable.original_amount.to_string(), "gross": gross.to_string(),
        "retention": retention.to_string(), "blocked": payable.blocked,
    }, operation_id=operation_id, entity_id=payable.id, branch_id=branch_id,
        source_document_id=document.id)
    if payable.blocked:
        publish_finance_event(uow, EventName.PAYABLE_BLOCKED, {
            "payable_id": payable.id, "reason": payable.block_reason,
        }, operation_id=operation_id, entity_id=payable.id, branch_id=branch_id)
    return payable


class CreatePayableUseCase:
    def __init__(self) -> None:
        self._engine = PostingEngine()

    def execute(self, connection, *, supplier_id: str, amount: str, currency_code: str = "MXN",
                document_number: str, issue_date: date, due_date: date | None = None,
                branch_id: str | None = None, source_module: str = "finance",
                source_document_id: str | None = None, operation_id: str,
                owns_transaction: bool = True, counterpart_account_id: str | None = None,
                debit_nature: PurchaseDebitNature | None = None,
                retention_amount: str | None = None,
                priority: PaymentPriority = PaymentPriority.NORMAL, payment_terms: str = "",
                early_payment_discount_percent: str | None = None,
                early_payment_discount_until: date | None = None,
                created_by: str | None = None) -> Payable:
        """``counterpart_account_id`` o ``debit_nature`` decide la cuenta del
        débito (nunca texto libre); desde Finanzas uno de los dos es obligatorio."""
        if counterpart_account_id is None and debit_nature is None \
                and source_module not in SELF_RECOGNIZING_SOURCES:
            raise FinanceDomainError(
                "Una cuenta por pagar creada desde Finanzas debe declarar la naturaleza o la "
                "cuenta del cargo (gasto, inventario o activo)")
        with FinanceUnitOfWork(connection, owns_transaction=owns_transaction) as uow:
            payable = create_payable_in(
                uow, supplier_id=supplier_id, amount=amount, currency_code=currency_code,
                document_number=document_number, issue_date=issue_date, due_date=due_date,
                branch_id=branch_id, source_module=source_module,
                source_document_id=source_document_id, operation_id=operation_id,
                retention_amount=retention_amount, priority=priority,
                payment_terms=payment_terms,
                debit_nature=debit_nature or PurchaseDebitNature.INVENTORY,
                early_payment_discount_percent=early_payment_discount_percent,
                early_payment_discount_until=early_payment_discount_until)
            recognizes = source_module not in SELF_RECOGNIZING_SOURCES
            if recognizes and not uow.journal_entries.find_by_posting_reference(
                    "finance", payable.id, PostingPurpose.PAYABLE_RECOGNITION):
                profile = require_profile(uow, "PURCHASE", issue_date, branch_id=branch_id)
                if counterpart_account_id is None and debit_nature not in NATURE_ROLE:
                    raise FinanceDomainError(
                        f"Un cargo de naturaleza {debit_nature.value} exige indicar su cuenta "
                        "(gasto anticipado u otro activo no tienen cuenta por omisión)")
                debit_account = counterpart_account_id or profile.account_for(
                    NATURE_ROLE[debit_nature])
                gross = payable.original_amount.add(payable.retention_amount)
                lines = [LineSpec(debit_account, debit=gross,
                                  description=f"Cargo CxP {document_number}",
                                  supplier_id=supplier_id),
                         LineSpec(profile.account_for("payable_account_id"),
                                  credit=payable.original_amount,
                                  description=f"CxP {document_number}", supplier_id=supplier_id)]
                if payable.retention_amount.is_positive():
                    lines.append(LineSpec(profile.account_for("retention_account_id"),
                                          credit=payable.retention_amount,
                                          description=f"Retención {document_number}",
                                          supplier_id=supplier_id))
                self._engine.post(
                    uow, JournalType.PURCHASES, issue_date, f"Reconocimiento CxP {document_number}",
                    PostingReference("finance", payable.id, PostingPurpose.PAYABLE_RECOGNITION,
                                     operation_id),
                    lines, currency_code=gross.currency_code, branch_id=branch_id,
                    created_by=created_by,
                    source_document_type=FinancialDocumentType.SUPPLIER_INVOICE.value)
            uow.audit(AuditAction.PAYABLE_CREATED, entity_type="payable", entity_id=payable.id,
                      operation_id=operation_id, user_id=created_by,
                      after={"supplier_id": supplier_id,
                             "amount": payable.original_amount.to_string(),
                             "retention": payable.retention_amount.to_string(),
                             "document_number": document_number, "blocked": payable.blocked},
                      branch_id=branch_id)
            return payable
