"""Seguimiento de cobranza (§11): disputas y promesas de pago.

Una CxC en disputa sigue debiéndose (no se castiga ni se cancela por estar en
disputa); queda marcada con motivo y quién la levantó hasta resolverse. La
promesa de pago es un compromiso del cliente que se cumple o se rompe.
"""

from __future__ import annotations

from datetime import date

from backend.domain.finance.entities.receivable import PaymentPromise
from backend.domain.finance.enums import AuditAction
from backend.domain.finance.exceptions import FinanceDomainError, ReceivableNotFoundError
from backend.domain.finance.value_objects.money import Money
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork


def _receivable(uow: FinanceUnitOfWork, receivable_id: str):
    receivable = uow.receivables.get(receivable_id)
    if receivable is None:
        raise ReceivableNotFoundError("La cuenta por cobrar no existe")
    return receivable


class DisputeReceivableUseCase:
    def open(self, connection, *, receivable_id: str, reason: str, operation_id: str,
             disputed_by: str) -> None:
        with FinanceUnitOfWork(connection) as uow:
            receivable = _receivable(uow, receivable_id)
            before = {"status": receivable.status.value}
            receivable.dispute(reason, disputed_by)
            uow.receivables.update(receivable)
            uow.audit(AuditAction.RECEIVABLE_DISPUTED, entity_type="receivable",
                      entity_id=receivable.id, operation_id=operation_id,
                      user_id=disputed_by, before=before,
                      after={"status": receivable.status.value}, reason=reason,
                      branch_id=receivable.branch_id)

    def resolve(self, connection, *, receivable_id: str, resolution: str, as_of: date,
                operation_id: str, resolved_by: str) -> None:
        if not (resolution or "").strip():
            raise FinanceDomainError("Resolver la disputa exige explicar la resolución")
        with FinanceUnitOfWork(connection) as uow:
            receivable = _receivable(uow, receivable_id)
            before = {"status": receivable.status.value,
                      "dispute_reason": receivable.dispute_reason}
            receivable.resolve_dispute(as_of)
            uow.receivables.update(receivable)
            uow.audit(AuditAction.RECEIVABLE_DISPUTED, entity_type="receivable",
                      entity_id=receivable.id, operation_id=operation_id,
                      user_id=resolved_by, before=before,
                      after={"status": receivable.status.value}, reason=resolution,
                      branch_id=receivable.branch_id)


class RegisterPaymentPromiseUseCase:
    def execute(self, connection, *, receivable_id: str, promised_date: date,
                promised_amount: str, operation_id: str, note: str = "",
                created_by: str | None = None) -> str:
        with FinanceUnitOfWork(connection) as uow:
            existing = uow.receivables.find_promise_by_operation_id(operation_id)
            if existing is not None:
                return existing["id"]
            receivable = _receivable(uow, receivable_id)
            if not receivable.is_open:
                raise FinanceDomainError(
                    f"No se promete el pago de una CxC {receivable.status.value}")
            amount = Money.from_string(promised_amount,
                                       receivable.outstanding_amount.currency_code)
            if amount > receivable.outstanding_amount:
                raise FinanceDomainError("La promesa excede el saldo por cobrar")
            promise = PaymentPromise.create(receivable.id, promised_date, amount, operation_id,
                                            note=note, created_by=created_by)
            uow.receivables.save_promise(promise)
            return promise.id

    def close(self, connection, *, promise_id: str, kept: bool) -> None:
        with FinanceUnitOfWork(connection) as uow:
            promise = uow.receivables.get_promise(promise_id)
            if promise is None:
                raise FinanceDomainError("La promesa de pago no existe")
            promise.close(kept)
            uow.receivables.update_promise(promise)
