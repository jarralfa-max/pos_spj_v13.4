"""Accounts payable use cases — segregated lifecycle.

Crear obligación → Programar pago → Autorizar → Ejecutar → Conciliar.
These operations are never combined into a single action.

Auditoría d9f2bca:
- F01: la CxP y su asiento de reconocimiento pueden escribirse en UNA
  transacción (``owns_transaction=False`` + ``create_in``), sin commit previo.
- F10: la misma operación con otro contenido es conflicto.
- F11: una CxP creada desde Finanzas declara su contrapartida y nace con asiento.
- F13: ejecutar revalida proveedor (existe, activo, sin bloqueo), cuenta
  beneficiaria para pagos bancarios, tesorería activa y de la misma moneda, y
  exige evidencia externa (referencia) que queda guardada con quien ejecutó.
  EXECUTED significa "contabilizado y liquidado con esta evidencia", no
  "confirmado por el banco": no hay integración bancaria.
"""

from __future__ import annotations

import json
from datetime import date

from backend.application.services.finance.posting_engine import PostingEngine
from backend.domain.finance.entities.financial_document import FinancialDocument
from backend.domain.finance.entities.payable import Payable, SupplierPayment
from backend.domain.finance.enums import (
    FinancialDocumentType,
    JournalType,
    PayableStatus,
    PostingPurpose,
    TreasuryAccountType,
)
from backend.domain.finance.exceptions import (
    CurrencyMismatchError,
    FinanceDomainError,
    IdempotencyConflictError,
    PaymentAuthorizationError,
)
from backend.domain.finance.services.journal_posting_service import LineSpec
from backend.domain.finance.services.payable_service import PayableService
from backend.domain.finance.value_objects.money import Money
from backend.domain.finance.value_objects.posting_reference import PostingReference
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.events.event_names import EventName
from backend.shared.ids import new_uuid

#: Orígenes que reconocen la obligación en su propio asiento, dentro de la
#: misma transacción (el puente de Compras).
_SELF_RECOGNIZING_SOURCES = frozenset({"procurement"})

#: Cuentas desde las que nunca se paga a un proveedor.
_FORBIDDEN_PAYMENT_SOURCES = {
    TreasuryAccountType.CASH_REGISTER:
        "Las compras no se pagan desde Caja POS. Use Tesorería/Capital o CxP.",
    TreasuryAccountType.DIGITAL_WALLET:
        "Un monedero promocional no es dinero; no paga proveedores.",
}


def _supplier_directory(connection, directory):
    if directory is not None:
        return directory
    from backend.infrastructure.integrations.finance_supplier_directory import (
        SqliteSupplierDirectory,
    )
    return SqliteSupplierDirectory(connection)


class CreatePayableUseCase:
    def __init__(self) -> None:
        self._engine = PostingEngine()

    def execute(self, connection, *, supplier_id: str, amount: str, currency_code: str = "MXN",
                document_number: str, issue_date: date, due_date: date | None = None,
                branch_id: str | None = None, source_module: str = "finance",
                source_document_id: str | None = None, operation_id: str,
                owns_transaction: bool = True, counterpart_account_id: str | None = None,
                created_by: str | None = None) -> Payable:
        if counterpart_account_id is None and source_module not in _SELF_RECOGNIZING_SOURCES:
            raise FinanceDomainError(
                "Una cuenta por pagar creada desde Finanzas debe declarar la cuenta de "
                "contrapartida de su reconocimiento (gasto, inventario o activo)")
        with FinanceUnitOfWork(connection, owns_transaction=owns_transaction) as uow:
            payable = self.create_in(
                uow, supplier_id=supplier_id, amount=amount, currency_code=currency_code,
                document_number=document_number, issue_date=issue_date, due_date=due_date,
                branch_id=branch_id, source_module=source_module,
                source_document_id=source_document_id, operation_id=operation_id)
            if counterpart_account_id is not None and not uow.journal_entries \
                    .find_by_posting_reference("finance", payable.id,
                                               PostingPurpose.PAYABLE_RECOGNITION):
                profile = uow.posting_profiles.find_effective("PURCHASE", issue_date,
                                                             branch_id=branch_id)
                if profile is None:
                    raise FinanceDomainError("No hay perfil contable PURCHASE vigente")
                money = payable.original_amount
                self._engine.post(
                    uow, JournalType.PURCHASES, issue_date,
                    f"Reconocimiento CxP {document_number}",
                    PostingReference("finance", payable.id,
                                     PostingPurpose.PAYABLE_RECOGNITION, operation_id),
                    [LineSpec(counterpart_account_id, debit=money,
                              description=f"Cargo CxP {document_number}"),
                     LineSpec(profile.account_for("payable_account_id"), credit=money,
                              description=f"CxP {document_number}")],
                    currency_code=money.currency_code, branch_id=branch_id,
                    created_by=created_by,
                )
            return payable

    @staticmethod
    def create_in(uow: FinanceUnitOfWork, *, supplier_id: str, amount: str,
                  currency_code: str, document_number: str, issue_date: date,
                  due_date: date | None, branch_id: str | None, source_module: str,
                  source_document_id: str | None, operation_id: str) -> Payable:
        """Crea documento + CxP dentro de una unidad de trabajo YA abierta."""
        money = Money.from_string(amount, currency_code)
        existing = uow.payables.find_by_operation_id(operation_id)
        if existing is not None:
            if (existing.supplier_id != supplier_id
                    or existing.original_amount.currency_code != money.currency_code
                    or existing.original_amount.amount != money.amount):
                raise IdempotencyConflictError(
                    f"La operación {operation_id} ya creó una CxP por "
                    f"{existing.original_amount.to_string()} a otro contenido")
            return existing
        document = FinancialDocument.create(
            FinancialDocumentType.SUPPLIER_INVOICE, document_number, issue_date, money,
            source_module, source_document_id or new_uuid(), new_uuid(),
            branch_id=branch_id, supplier_id=supplier_id, due_date=due_date,
        )
        uow.financial_documents.save(document)
        payable = PayableService().create_obligation(
            supplier_id, document.id, money, issue_date, operation_id,
            due_date=due_date, branch_id=branch_id,
        )
        uow.payables.save(payable)
        uow.outbox.enqueue(
            event_id=new_uuid(), event_name=EventName.PAYABLE_CREATED.value,
            payload_json=json.dumps({
                "payable_id": payable.id, "supplier_id": supplier_id,
                "amount": money.to_string(),
            }),
            operation_id=operation_id,
        )
        return payable


def _validate_payment_context(uow: FinanceUnitOfWork, directory, *, payable: Payable,
                              treasury_account_id: str, amount: Money) -> None:
    """Reglas que deben seguir siendo ciertas al programar Y al ejecutar."""
    if payable.status is PayableStatus.CANCELLED:
        raise FinanceDomainError("La cuenta por pagar está cancelada")
    treasury_account = uow.treasury.get(treasury_account_id)
    if treasury_account is None or not treasury_account.active:
        raise FinanceDomainError("La cuenta de tesorería no existe o está inactiva")
    forbidden = _FORBIDDEN_PAYMENT_SOURCES.get(treasury_account.account_type)
    if forbidden:
        raise FinanceDomainError(forbidden)
    if treasury_account.currency_code != amount.currency_code:
        raise CurrencyMismatchError(
            f"La deuda está en {amount.currency_code} y la cuenta {treasury_account.name} "
            f"en {treasury_account.currency_code}")
    eligibility = directory.payment_eligibility(payable.supplier_id)
    if not eligibility.eligible:
        raise PaymentAuthorizationError(eligibility.reason)
    if treasury_account.account_type is TreasuryAccountType.BANK and not eligibility.bank_account:
        raise PaymentAuthorizationError(
            f"El proveedor {eligibility.name} no tiene cuenta bancaria registrada; "
            "un pago por banco necesita beneficiario")


class ScheduleSupplierPaymentUseCase:
    def __init__(self, supplier_directory=None) -> None:
        self._directory = supplier_directory

    def execute(self, connection, *, payable_id: str, amount: str, scheduled_date: date,
                treasury_account_id: str, scheduled_by: str, reference: str = "",
                operation_id: str) -> SupplierPayment:
        with FinanceUnitOfWork(connection) as uow:
            duplicate = uow.supplier_payments.find_by_operation_id(operation_id)
            if duplicate is not None:
                return duplicate
            payable = uow.payables.get(payable_id)
            if payable is None:
                raise FinanceDomainError("La cuenta por pagar no existe")
            money = Money.from_string(amount, payable.original_amount.currency_code)
            _validate_payment_context(uow, _supplier_directory(connection, self._directory),
                                      payable=payable, treasury_account_id=treasury_account_id,
                                      amount=money)
            if money > payable.outstanding_amount:
                raise FinanceDomainError("El pago programado excede el saldo de la CxP")
            payment = PayableService().schedule_payment(
                payable, money, scheduled_date, treasury_account_id, operation_id,
                scheduled_by=scheduled_by, reference=reference,
            )
            uow.supplier_payments.save(payment)
            uow.outbox.enqueue(
                event_id=new_uuid(), event_name=EventName.SUPPLIER_PAYMENT_SCHEDULED.value,
                payload_json=json.dumps({
                    "payment_id": payment.id, "payable_id": payable_id,
                    "amount": money.to_string(),
                }),
                operation_id=operation_id,
            )
            return payment


class AuthorizeSupplierPaymentUseCase:
    def execute(self, connection, *, payment_id: str, authorized_by: str,
                operation_id: str) -> SupplierPayment:
        with FinanceUnitOfWork(connection) as uow:
            payment = uow.supplier_payments.get(payment_id)
            if payment is None:
                raise FinanceDomainError("El pago programado no existe")
            PayableService().authorize_payment(payment, authorized_by)
            uow.supplier_payments.update(payment)
            uow.outbox.enqueue(
                event_id=new_uuid(), event_name=EventName.SUPPLIER_PAYMENT_AUTHORIZED.value,
                payload_json=json.dumps({"payment_id": payment.id,
                                         "authorized_by": authorized_by}),
                operation_id=operation_id,
            )
            return payment


class ExecuteSupplierPaymentUseCase:
    def __init__(self, supplier_directory=None) -> None:
        self._engine = PostingEngine()
        self._directory = supplier_directory

    def execute(self, connection, *, payment_id: str, executed_date: date,
                operation_id: str, executed_by: str | None = None,
                execution_reference: str = "") -> SupplierPayment:
        with FinanceUnitOfWork(connection) as uow:
            payment = uow.supplier_payments.get(payment_id)
            if payment is None:
                raise FinanceDomainError("El pago programado no existe")
            existing = uow.journal_entries.find_by_posting_reference(
                "finance", payment.id, PostingPurpose.SUPPLIER_PAYMENT)
            if existing is not None:
                return payment  # already executed (idempotent)
            if not (execution_reference or "").strip():
                raise PaymentAuthorizationError(
                    "Registre la evidencia del pago (folio SPEI, cheque o recibo); "
                    "sin ella el pago no se marca como ejecutado")
            payable = uow.payables.get(payment.payable_id)
            if payable is None:
                raise FinanceDomainError("La CxP del pago no existe")
            # Lo autorizado ayer puede no valer hoy: se revalida todo el contexto.
            _validate_payment_context(uow, _supplier_directory(connection, self._directory),
                                      payable=payable,
                                      treasury_account_id=payment.treasury_account_id,
                                      amount=payment.amount)
            if payment.amount > payable.outstanding_amount:
                raise FinanceDomainError(
                    "El pago excede el saldo vigente de la CxP; vuelva a programarlo")
            treasury_account = uow.treasury.get(payment.treasury_account_id)
            profile = uow.posting_profiles.find_effective("PURCHASE", executed_date,
                                                         branch_id=payment.branch_id)
            if profile is None:
                raise FinanceDomainError("No hay perfil contable PURCHASE vigente")

            entry = self._engine.post(
                uow, JournalType.BANK, executed_date,
                f"Pago a proveedor {payment.reference or payment.id[:8]}",
                PostingReference("finance", payment.id, PostingPurpose.SUPPLIER_PAYMENT,
                                 operation_id),
                [
                    LineSpec(profile.account_for("payable_account_id"), debit=payment.amount,
                             description="Cancelación de CxP"),
                    LineSpec(treasury_account.ledger_account_id, credit=payment.amount,
                             description=f"Salida de tesorería ({execution_reference.strip()})"),
                ],
                currency_code=payment.amount.currency_code,
                branch_id=payment.branch_id, created_by=executed_by,
            )
            PayableService().execute_payment(payment, payable, executed_date, entry.id)
            payment.executed_by = executed_by
            payment.execution_reference = execution_reference.strip()
            uow.supplier_payments.update(payment)
            uow.payables.update(payable)
            document = uow.financial_documents.get(payable.financial_document_id)
            if document is not None:
                document.apply_settlement(payment.amount)
                uow.financial_documents.update(document)
            uow.outbox.enqueue(
                event_id=new_uuid(), event_name=EventName.SUPPLIER_PAYMENT_EXECUTED.value,
                payload_json=json.dumps({
                    "payment_id": payment.id, "journal_entry_id": entry.id,
                    "amount": payment.amount.to_string(),
                    "execution_reference": payment.execution_reference,
                    "executed_by": executed_by,
                }),
                operation_id=new_uuid(),
            )
            return payment
