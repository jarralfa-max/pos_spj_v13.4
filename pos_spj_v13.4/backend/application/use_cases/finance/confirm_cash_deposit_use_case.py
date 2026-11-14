"""ConfirmCashDepositUseCase — Tesorería confirma el depósito con su ticket (SDLC-CASH-002).

Caja prepara el paquete; quien confirma que el dinero llegó al banco es Tesorería
(respuesta del responsable: tesorería, con ticket). La confirmación y el evento
`TREASURY_CASH_DEPOSIT_CONFIRMED` nacen en la misma transacción; el despachador
del `finance_outbox` lo entrega a `TreasuryCashDepositConfirmedHandler`, que
asienta Dr banco / Cr caja con la referencia del `deposit_id`. Hay una sola
confirmación por depósito, así que hay un solo asiento.
"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.application.services.finance.posting_engine import publish_finance_event
from backend.domain.finance.enums import AuditAction
from backend.domain.finance.exceptions import FinanceDomainError, PermissionDeniedError
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.infrastructure.integrations.treasury_cash_deposits import (
    TreasuryCashDepositGateway,
)
from backend.shared.events.event_names import EventName


class ConfirmCashDepositUseCase:
    def execute(self, connection, *, deposit_id: str, ticket_reference: str,
                confirmed_by: str, operation_id: str) -> str:
        ticket = ticket_reference.strip()
        if not ticket:
            raise FinanceDomainError("Confirmar el depósito requiere el ticket del banco")
        deposits = TreasuryCashDepositGateway(connection)
        with FinanceUnitOfWork(connection) as uow:
            prior = deposits.find_confirmation(deposit_id)
            if prior:
                return prior["id"]
            deposit = deposits.get(deposit_id)
            if deposit is None or deposit["status"] == "CANCELLED":
                raise FinanceDomainError("El depósito no existe o está cancelado")
            if confirmed_by == deposit["prepared_by"]:
                raise PermissionDeniedError(
                    "Tesorería debe confirmar con un usuario distinto al que preparó")
            confirmation_id = deposits.add_confirmation(
                deposit_id=deposit_id, branch_id=deposit["branch_id"],
                amount=deposit["amount"], ticket_reference=ticket, confirmed_by=confirmed_by,
                operation_id=operation_id,
                confirmed_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
            uow.audit(AuditAction.TREASURY_MOVEMENT, entity_type="cash_deposit",
                      entity_id=deposit_id, operation_id=operation_id, user_id=confirmed_by,
                      after={"amount": deposit["amount"], "ticket_reference": ticket})
            # El sobre lleva `payload` anidado: es lo que lee `CashFinanceEventRouter`.
            publish_finance_event(uow, EventName.TREASURY_CASH_DEPOSIT_CONFIRMED, {"payload": {
                "deposit_id": deposit_id, "amount": deposit["amount"],
                "ticket_reference": ticket, "handover_id": deposit["handover_id"],
            }}, operation_id=operation_id, entity_id=deposit_id,
                branch_id=deposit["branch_id"])
        return confirmation_id
