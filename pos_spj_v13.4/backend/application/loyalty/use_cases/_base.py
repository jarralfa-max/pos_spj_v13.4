"""Shared plumbing for Fidelidad/Loyalty use cases — authorization
injection and outbox event emission. Mirrors
backend/application/sales/use_cases/_base.py exactly.

LOY-29: `_emit` also writes the audit trail (`record_event_audit`) on the
same Unit-of-Work connection — every published fact is audited (§61).
"""

from __future__ import annotations

import json

from backend.application.loyalty.authorization import LoyaltyAuthorizationPolicy
from backend.domain.loyalty.events import loyalty_event_payload
from backend.application.shared.event_audit import record_event_audit


#: Eventos del libro de puntos: su `entity_id` es la transacción del libro.
_LEDGER_EVENTS = frozenset({
    "LOYALTY_POINTS_ISSUED", "LOYALTY_POINTS_RESERVED", "LOYALTY_POINTS_REDEEMED",
    "LOYALTY_POINTS_RELEASED", "LOYALTY_POINTS_EXPIRED", "LOYALTY_POINTS_ADJUSTED",
    "LOYALTY_TRANSACTION_REVERSED",
})


def _ledger_fields(uow, transaction_id: str) -> dict:
    """Arquitectura híbrida, Slice 6: a quién pertenece la transacción y cómo
    cuenta en el saldo, tal como lo decide `LoyaltyBalancePolicy` aquí. El
    servidor central suma lo mismo, consolidado entre sucursales, sin volver a
    implementar la regla."""
    transaccion = uow.transactions.get(transaction_id)
    if transaccion is None:
        return {}
    cuenta = uow.accounts.get(transaccion.loyalty_account_id)
    return {"ledger": {
        "transaction_id": transaccion.id,
        "loyalty_account_id": transaccion.loyalty_account_id,
        "customer_id": getattr(cuenta, "customer_id", None),
        "membership_id": transaccion.membership_id,
        "transaction_type": getattr(transaccion.transaction_type, "value",
                                    transaccion.transaction_type),
        "status": getattr(transaccion.status, "value", transaccion.status),
        "points_amount": str(transaccion.points_amount),
        "counts_toward_balance": bool(transaccion.counts_toward_balance()),
        "sale_id": transaccion.sale_id,
    }}


class _LoyaltyBaseUseCase:
    def __init__(self, authorization: LoyaltyAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or LoyaltyAuthorizationPolicy()

    @staticmethod
    def _emit(uow, event_name: str, *, entity_id: str, operation_id: str,
              branch_id: str, actor_user_id: str, **extra) -> None:
        if event_name in _LEDGER_EVENTS:
            extra = {**_ledger_fields(uow, entity_id), **extra}
        payload = loyalty_event_payload(
            event_name, operation_id=operation_id, entity_id=entity_id,
            branch_id=branch_id, user_id=actor_user_id, **extra)
        uow.outbox.enqueue(
            event_id=payload["event_id"], event_name=event_name,
            payload_json=json.dumps(payload, ensure_ascii=False, default=str),
            operation_id=operation_id)
        # §61 (LOY-29): todo hecho publicado deja rastro en `audit_logs`, en la
        # misma transacción.
        record_event_audit(
            uow.connection, module="GROWTH_ENGINE", entity="fidelidad", event_name=event_name,
            entity_id=entity_id, operation_id=operation_id, branch_id=branch_id,
            actor_user_id=actor_user_id, details=extra)

    @staticmethod
    def _audit(uow, action: str, *, entity_id: str, operation_id: str, branch_id: str,
               actor_user_id: str, **extra) -> None:
        """Transición sin evento canónico en §62 (aprobar, suspender…): no va al
        outbox, pero sí a la auditoría (§61, LOY-29)."""
        record_event_audit(
            uow.connection, module="GROWTH_ENGINE", entity="fidelidad", event_name=action,
            entity_id=entity_id, operation_id=operation_id, branch_id=branch_id,
            actor_user_id=actor_user_id, details=extra)
