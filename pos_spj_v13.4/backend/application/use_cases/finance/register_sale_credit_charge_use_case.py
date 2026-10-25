"""Cargos a crédito de una venta (auditoría F03 / Ventas V02).

La deuda es TOTAL POR VENTA: un documento y una CxC por venta, y cada pago a
crédito suma su cargo con la identidad del pago (``receivable_charges``).
Pagos de 10 y 20 → deuda 30; repetir cualquiera de los dos no la cambia. El
asiento lo hace Ventas al completar la venta, por el total a crédito.
"""

from __future__ import annotations

from datetime import date

from backend.application.use_cases.finance.create_receivable_use_case import (
    create_receivable_in,
)
from backend.domain.finance.entities.receivable import Receivable
from backend.domain.finance.enums import FinancialDocumentType
from backend.domain.finance.exceptions import FinanceDomainError, IdempotencyConflictError
from backend.domain.finance.value_objects.money import Money
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork


class RegisterSaleCreditChargeUseCase:
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
            receivable = document = None
            for candidate in uow.financial_documents.find_by_source("sales", sale_id):
                if candidate.document_type is FinancialDocumentType.CUSTOMER_INVOICE:
                    document = candidate
                    receivable = uow.receivables.find_by_document(candidate.id)
                    break
            if receivable is None:
                receivable = create_receivable_in(
                    uow, customer_id=customer_id, money=money, document_number=folio or sale_id,
                    issue_date=issue_date, due_date=due_date, branch_id=branch_id,
                    source_module="sales", source_document_id=sale_id,
                    operation_id=f"{sale_id}:receivable")
            else:
                if receivable.customer_id != customer_id:
                    raise FinanceDomainError("La venta ya tiene deuda a nombre de otro cliente")
                receivable.add_charge(money)
                uow.receivables.update(receivable)
                document.increase_total(money)
                uow.financial_documents.update(document)
            uow.receivable_charges.add(
                receivable_id=receivable.id, amount=money.to_string(),
                currency_code=money.currency_code, source_module="sales",
                source_reference=payment_id, operation_id=charge_operation)
            return receivable


class VoidSaleCreditChargeUseCase:
    """Anula el cargo a crédito de UN pago de una venta que todavía no se cierra
    (Ventas V02). Idempotente; deja un renglón negativo como rastro. No hay
    asiento que revertir: el de la venta a crédito lo hace Ventas al completarla."""

    def execute(self, connection, *, sale_id: str, payment_id: str,
                owns_transaction: bool = True) -> Receivable | None:
        charge_operation = f"{sale_id}:{payment_id}:credit-charge"
        void_operation = f"{charge_operation}-void"
        with FinanceUnitOfWork(connection, owns_transaction=owns_transaction) as uow:
            charge = uow.receivable_charges.find_by_operation_id(charge_operation)
            if charge is None:
                return None            # ese pago nunca cargó deuda
            receivable = uow.receivables.get(charge["receivable_id"])
            if uow.receivable_charges.find_by_operation_id(void_operation) is not None:
                return receivable      # reintento
            money = Money.from_string(charge["amount"], charge["currency_code"])
            receivable.remove_charge(money)
            uow.receivables.update(receivable)
            document = uow.financial_documents.get(receivable.financial_document_id)
            if document is not None:
                document.decrease_total(money)
                uow.financial_documents.update(document)
            uow.receivable_charges.add(
                receivable_id=receivable.id, amount=f"-{money.to_string()}",
                currency_code=money.currency_code, source_module="sales",
                source_reference=payment_id, operation_id=void_operation)
            return receivable
