"""Accounts receivable use cases — create receivables and register collections.

Auditoría d9f2bca:
- F03: una venta con varios pagos a crédito debe la SUMA. ``RegisterSaleCreditChargeUseCase``
  identifica cada cargo por el pago que lo origina; repetir un pago no cambia nada.
- F06: un cobro sólo entra a una cuenta de tesorería de la moneda de la deuda.
- F10: la misma operación con otro contenido es un conflicto, no un éxito.
- F11: una CxC creada desde Finanzas nace con su asiento de reconocimiento; sin
  contrapartida sólo la crea un módulo operativo que la reconoce él mismo.
"""

from __future__ import annotations

import json
from datetime import date

from backend.application.services.finance.posting_engine import PostingEngine
from backend.domain.finance.entities.financial_document import FinancialDocument
from backend.domain.finance.entities.receivable import Receivable
from backend.domain.finance.enums import (
    FinancialDocumentType,
    JournalType,
    PostingPurpose,
    TreasuryAccountType,
)
from backend.domain.finance.exceptions import (
    CurrencyMismatchError,
    FinanceDomainError,
    IdempotencyConflictError,
)
from backend.domain.finance.services.journal_posting_service import LineSpec
from backend.domain.finance.services.receivable_service import ReceivableService
from backend.domain.finance.value_objects.money import Money
from backend.domain.finance.value_objects.posting_reference import PostingReference
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.events.event_names import EventName
from backend.shared.ids import new_uuid

#: Módulos operativos que reconocen la deuda en su propio asiento (Ventas lo
#: hace al completar la venta). Cualquier otro origen debe declarar contrapartida.
_SELF_RECOGNIZING_SOURCES = frozenset({"sales"})


def _same_receivable_or_conflict(existing: Receivable, customer_id: str, money: Money) -> Receivable:
    if existing.customer_id != customer_id or existing.original_amount.currency_code != money.currency_code:
        raise IdempotencyConflictError(
            f"La operación {existing.operation_id} ya creó una CxC de otro cliente o moneda")
    return existing


class CreateReceivableUseCase:
    """Creates a receivable (with its source document)."""

    def __init__(self) -> None:
        self._engine = PostingEngine()

    def execute(self, connection, *, customer_id: str, amount: str, currency_code: str = "MXN",
                document_number: str, issue_date: date, due_date: date | None = None,
                branch_id: str | None = None, source_module: str = "finance",
                source_document_id: str | None = None, operation_id: str,
                owns_transaction: bool = True,
                counterpart_account_id: str | None = None,
                created_by: str | None = None) -> Receivable:
        """``owns_transaction=False``: la deuda se escribe dentro de la transacción
        de quien llama (la venta) y se confirma o revierte junto con ella.

        ``counterpart_account_id``: cuenta del haber del asiento de
        reconocimiento (Dr Clientes / Cr contrapartida). Obligatoria salvo
        para un módulo que reconoce la deuda en su propio asiento."""
        money = Money.from_string(amount, currency_code)
        if counterpart_account_id is None and source_module not in _SELF_RECOGNIZING_SOURCES:
            raise FinanceDomainError(
                "Una cuenta por cobrar creada desde Finanzas debe declarar la cuenta de "
                "contrapartida de su reconocimiento; sin asiento el auxiliar y el mayor "
                "dejarían de cuadrar")
        with FinanceUnitOfWork(connection, owns_transaction=owns_transaction) as uow:
            existing = uow.receivables.find_by_operation_id(operation_id)
            if existing is not None:
                if existing.original_amount.amount != money.amount:
                    raise IdempotencyConflictError(
                        f"La operación {operation_id} ya creó una CxC por "
                        f"{existing.original_amount.to_string()}; no se acepta "
                        f"{money.to_string()} con la misma clave")
                return _same_receivable_or_conflict(existing, customer_id, money)
            receivable = self._create(
                uow, customer_id=customer_id, money=money, document_number=document_number,
                issue_date=issue_date, due_date=due_date, branch_id=branch_id,
                source_module=source_module, source_document_id=source_document_id,
                operation_id=operation_id)
            if counterpart_account_id is not None:
                profile = uow.posting_profiles.find_effective("SALE", issue_date,
                                                             branch_id=branch_id)
                if profile is None:
                    raise FinanceDomainError("No hay perfil contable SALE vigente")
                self._engine.post(
                    uow, JournalType.GENERAL, issue_date,
                    f"Reconocimiento CxC {document_number}",
                    PostingReference("finance", receivable.id,
                                     PostingPurpose.RECEIVABLE_RECOGNITION, operation_id),
                    [LineSpec(profile.account_for("receivable_account_id"), debit=money,
                              description=f"CxC {document_number}"),
                     LineSpec(counterpart_account_id, credit=money,
                              description=f"Contrapartida CxC {document_number}")],
                    currency_code=money.currency_code, branch_id=branch_id,
                    created_by=created_by,
                )
            return receivable

    @staticmethod
    def _create(uow, *, customer_id: str, money: Money, document_number: str,
                issue_date: date, due_date: date | None, branch_id: str | None,
                source_module: str, source_document_id: str | None,
                operation_id: str) -> Receivable:
        document = FinancialDocument.create(
            FinancialDocumentType.SALES_INVOICE, document_number, issue_date, money,
            source_module, source_document_id or new_uuid(), new_uuid(),
            branch_id=branch_id, customer_id=customer_id, due_date=due_date,
        )
        uow.financial_documents.save(document)
        receivable = Receivable.create(
            customer_id, document.id, money, issue_date, operation_id,
            due_date=due_date, branch_id=branch_id,
        )
        uow.receivables.save(receivable)
        uow.outbox.enqueue(
            event_id=new_uuid(), event_name=EventName.RECEIVABLE_CREATED.value,
            payload_json=json.dumps({
                "receivable_id": receivable.id, "customer_id": customer_id,
                "amount": money.to_string(), "currency_code": money.currency_code,
            }),
            operation_id=operation_id,
        )
        return receivable


class RegisterSaleCreditChargeUseCase:
    """Un pago a crédito de una venta (auditoría F03).

    La deuda es TOTAL POR VENTA: un documento y una CxC por venta (el esquema
    exige un documento por origen), y cada pago a crédito suma su cargo con la
    identidad del pago (``receivable_charges``). Pagos de 10 y 20 → deuda 30;
    repetir cualquiera de los dos no la cambia. El asiento lo hace Ventas al
    completar la venta, por el total a crédito: auxiliar y mayor coinciden.
    """

    def execute(self, connection, *, customer_id: str, sale_id: str, payment_id: str,
                folio: str, amount: str, currency_code: str = "MXN",
                issue_date: date, due_date: date | None = None,
                branch_id: str | None = None, owns_transaction: bool = True) -> Receivable:
        if not payment_id:
            raise FinanceDomainError("Un cargo a crédito requiere la identidad del pago")
        money = Money.from_string(amount, currency_code)
        charge_operation = f"{sale_id}:{payment_id}:credit-charge"
        with FinanceUnitOfWork(connection, owns_transaction=owns_transaction) as uow:
            previous = uow.receivable_charges.find_by_operation_id(charge_operation)
            if previous is not None:
                if Money.from_string(previous["amount"], previous["currency_code"]).amount \
                        != money.amount:
                    raise IdempotencyConflictError(
                        f"El pago {payment_id} ya cargó {previous['amount']} a la venta; "
                        f"no se acepta {money.to_string()} con la misma identidad")
                return uow.receivables.get(previous["receivable_id"])
            receivable = None
            document = None
            for candidate in uow.financial_documents.find_by_source("sales", sale_id):
                if candidate.document_type is FinancialDocumentType.SALES_INVOICE:
                    document = candidate
                    receivable = uow.receivables.find_by_document(candidate.id)
                    break
            if receivable is None:
                receivable = CreateReceivableUseCase._create(
                    uow, customer_id=customer_id, money=money, document_number=folio or sale_id,
                    issue_date=issue_date, due_date=due_date, branch_id=branch_id,
                    source_module="sales", source_document_id=sale_id,
                    operation_id=f"{sale_id}:receivable")
            else:
                if receivable.customer_id != customer_id:
                    raise FinanceDomainError(
                        "La venta ya tiene deuda a nombre de otro cliente")
                receivable.add_charge(money)
                uow.receivables.update(receivable)
                document.increase_total(money)
                uow.financial_documents.update(document)
            uow.receivable_charges.add(
                receivable_id=receivable.id, amount=money.to_string(),
                currency_code=money.currency_code, source_module="sales",
                source_reference=payment_id, operation_id=charge_operation)
            return receivable


class RegisterCollectionUseCase:
    """Registers a customer payment: updates CxC and posts Dr treasury / Cr CxC."""

    def __init__(self) -> None:
        self._engine = PostingEngine()
        self._domain = ReceivableService()

    def execute(self, connection, *, receivable_id: str, amount: str,
                treasury_account_id: str, collection_date: date,
                reference: str = "", operation_id: str,
                created_by: str | None = None) -> str:
        with FinanceUnitOfWork(connection) as uow:
            duplicate = uow.collections.find_by_operation_id(operation_id)
            if duplicate is not None:
                if duplicate.receivable_id != receivable_id or \
                        duplicate.amount.amount != Money.from_string(
                            amount, duplicate.amount.currency_code).amount:
                    raise IdempotencyConflictError(
                        f"La operación {operation_id} ya registró otro cobro")
                return duplicate.id
            receivable = uow.receivables.get(receivable_id)
            if receivable is None:
                raise FinanceDomainError("La cuenta por cobrar no existe")
            treasury_account = uow.treasury.get(treasury_account_id)
            if treasury_account is None or not treasury_account.active:
                raise FinanceDomainError("La cuenta de tesorería no existe o está inactiva")
            if treasury_account.account_type is TreasuryAccountType.DIGITAL_WALLET:
                raise FinanceDomainError(
                    "Un monedero promocional no puede recibir cobros de clientes"
                )
            currency = receivable.original_amount.currency_code
            if treasury_account.currency_code != currency:
                raise CurrencyMismatchError(
                    f"La deuda está en {currency} y la cuenta {treasury_account.name} en "
                    f"{treasury_account.currency_code}; no se cobra sin conversión explícita")
            money = Money.from_string(amount, currency)

            collection = self._domain.register_collection(
                receivable, money, collection_date, treasury_account_id, operation_id,
                reference=reference,
            )
            document = uow.financial_documents.get(receivable.financial_document_id)
            if document is not None:
                document.apply_settlement(money)
                uow.financial_documents.update(document)

            profile = self._resolve_sale_profile(uow, collection_date, receivable.branch_id)
            entry = self._engine.post(
                uow, JournalType.CASH, collection_date,
                f"Cobro CxC {reference or receivable.id[:8]}",
                PostingReference("finance", collection.id, PostingPurpose.COLLECTION,
                                 new_uuid()),
                [
                    LineSpec(treasury_account.ledger_account_id, debit=money,
                             description="Entrada de tesorería por cobro"),
                    LineSpec(profile.account_for("receivable_account_id"), credit=money,
                             description="Aplicación a cuentas por cobrar"),
                ],
                currency_code=currency, branch_id=receivable.branch_id, created_by=created_by,
            )
            collection.journal_entry_id = entry.id
            uow.collections.save(collection)
            uow.receivables.update(receivable)

            uow.outbox.enqueue(
                event_id=new_uuid(), event_name=EventName.COLLECTION_REGISTERED.value,
                payload_json=json.dumps({
                    "collection_id": collection.id, "receivable_id": receivable.id,
                    "amount": money.to_string(),
                    "outstanding": receivable.outstanding_amount.to_string(),
                }),
                operation_id=operation_id,
            )
            if receivable.outstanding_amount.is_zero():
                uow.outbox.enqueue(
                    event_id=new_uuid(), event_name=EventName.RECEIVABLE_SETTLED.value,
                    payload_json=json.dumps({"receivable_id": receivable.id}),
                    operation_id=new_uuid(),
                )
            return collection.id

    @staticmethod
    def _resolve_sale_profile(uow: FinanceUnitOfWork, on_date: date, branch_id: str | None = None):
        profile = uow.posting_profiles.find_effective("SALE", on_date, branch_id=branch_id)
        if profile is None:
            raise FinanceDomainError("No hay perfil contable SALE vigente")
        return profile
