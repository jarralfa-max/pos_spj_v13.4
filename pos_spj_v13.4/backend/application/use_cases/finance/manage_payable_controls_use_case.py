"""Controles sobre una CxP (§12): bloqueo/desbloqueo, disputa y cancelación de pagos.

Desbloquear un documento detenido por diferencia de recepción exige permiso
propio (``FINANZAS.cxp.desbloquear``, en la capa de comandos) y motivo.
Cancelar un pago programado/autorizado lo saca del flujo sin tocar saldos.
"""

from __future__ import annotations

from datetime import date

from backend.application.services.finance.posting_engine import publish_finance_event
from backend.domain.finance.enums import AuditAction
from backend.domain.finance.exceptions import FinanceDomainError, PayableNotFoundError
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.events.event_names import EventName


def _payable(uow: FinanceUnitOfWork, payable_id: str):
    payable = uow.payables.get(payable_id)
    if payable is None:
        raise PayableNotFoundError("La cuenta por pagar no existe")
    return payable


def _snapshot(payable) -> dict:
    return {"status": payable.status.value, "blocked": payable.blocked,
            "block_reason": payable.block_reason, "dispute_reason": payable.dispute_reason}


class ManagePayableControlsUseCase:
    def block(self, connection, *, payable_id: str, reason: str, operation_id: str,
              actor: str) -> None:
        with FinanceUnitOfWork(connection) as uow:
            payable = _payable(uow, payable_id)
            before = _snapshot(payable)
            payable.block(reason)
            uow.payables.update(payable)
            uow.audit(AuditAction.PAYABLE_BLOCKED, entity_type="payable", entity_id=payable.id,
                      operation_id=operation_id, user_id=actor, before=before,
                      after=_snapshot(payable), reason=reason, branch_id=payable.branch_id)
            publish_finance_event(uow, EventName.PAYABLE_BLOCKED, {
                "payable_id": payable.id, "reason": reason,
            }, operation_id=operation_id, entity_id=payable.id, branch_id=payable.branch_id)

    def unblock(self, connection, *, payable_id: str, reason: str, operation_id: str,
                actor: str) -> None:
        with FinanceUnitOfWork(connection) as uow:
            payable = _payable(uow, payable_id)
            before = _snapshot(payable)
            payable.unblock(actor, reason)
            uow.payables.update(payable)
            uow.audit(AuditAction.PAYABLE_BLOCKED, entity_type="payable", entity_id=payable.id,
                      operation_id=operation_id, user_id=actor, before=before,
                      after=_snapshot(payable), reason=reason, branch_id=payable.branch_id)

    def dispute(self, connection, *, payable_id: str, reason: str, operation_id: str,
                actor: str) -> None:
        with FinanceUnitOfWork(connection) as uow:
            payable = _payable(uow, payable_id)
            before = _snapshot(payable)
            payable.dispute(reason)
            uow.payables.update(payable)
            uow.audit(AuditAction.PAYABLE_BLOCKED, entity_type="payable", entity_id=payable.id,
                      operation_id=operation_id, user_id=actor, before=before,
                      after=_snapshot(payable), reason=reason, branch_id=payable.branch_id)

    def resolve_dispute(self, connection, *, payable_id: str, resolution: str, as_of: date,
                        operation_id: str, actor: str) -> None:
        if not (resolution or "").strip():
            raise FinanceDomainError("Resolver la disputa exige explicar la resolución")
        with FinanceUnitOfWork(connection) as uow:
            payable = _payable(uow, payable_id)
            before = _snapshot(payable)
            payable.resolve_dispute(as_of)
            uow.payables.update(payable)
            uow.audit(AuditAction.PAYABLE_BLOCKED, entity_type="payable", entity_id=payable.id,
                      operation_id=operation_id, user_id=actor, before=before,
                      after=_snapshot(payable), reason=resolution, branch_id=payable.branch_id)

    def cancel_payment(self, connection, *, payment_id: str, reason: str, operation_id: str,
                       actor: str, as_of: date) -> None:
        if not (reason or "").strip():
            raise FinanceDomainError("Cancelar un pago exige el motivo")
        with FinanceUnitOfWork(connection) as uow:
            payment = uow.supplier_payments.get(payment_id)
            if payment is None:
                raise FinanceDomainError("El pago programado no existe")
            before = {"status": payment.status.value}
            payment.cancel()
            uow.supplier_payments.update(payment)
            payable = _payable(uow, payment.payable_id)
            if not uow.supplier_payments.in_flight_amount(payable.id):
                payable.release_payment_stage(as_of)
                uow.payables.update(payable)
            uow.audit(AuditAction.PAYMENT_SCHEDULED, entity_type="supplier_payment",
                      entity_id=payment.id, operation_id=operation_id, user_id=actor,
                      before=before, after={"status": payment.status.value}, reason=reason,
                      branch_id=payment.branch_id)
