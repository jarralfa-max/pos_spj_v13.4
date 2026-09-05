# domain/whatsapp/entities/business_operation.py — WA-10 (§19 del prompt maestro)
"""BusinessOperationIdempotencyRecord — respalda `whatsapp_business_operation_idempotency`
(WA-3, migración 243), sin repositorio propio hasta esta fase. El primer
consumidor real es la confirmación de pedido (§34): "dos mensajes
distintos, misma acción de negocio" (p. ej. "confirmar pedido" y "sí,
confirmar") deben producir el MISMO resultado, no dos pedidos."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from domain.whatsapp._ids import new_id
from domain.whatsapp.enums import IdempotencyStatus
from domain.whatsapp.exceptions import WhatsAppDomainError


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class IdempotencyRecordAlreadyFinalizedError(WhatsAppDomainError):
    pass


@dataclass
class BusinessOperationIdempotencyRecord:
    id: str
    operation_id: str
    operation_type: str
    aggregate_type: str
    aggregate_id: Optional[str]
    fingerprint: str
    status: IdempotencyStatus
    result_reference: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]

    @classmethod
    def start(
        cls, *, operation_type: str, aggregate_type: str, aggregate_id: Optional[str], fingerprint: str
    ) -> "BusinessOperationIdempotencyRecord":
        if not fingerprint:
            raise ValueError("fingerprint es obligatorio")
        if not operation_type:
            raise ValueError("operation_type es obligatorio")
        return cls(
            id=new_id(),
            operation_id=new_id(),
            operation_type=operation_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            fingerprint=fingerprint,
            status=IdempotencyStatus.PENDING,
            result_reference=None,
            created_at=_utcnow(),
            completed_at=None,
        )

    def complete(self, result_reference: str) -> None:
        if self.status != IdempotencyStatus.PENDING:
            raise IdempotencyRecordAlreadyFinalizedError(
                f"BusinessOperationIdempotencyRecord {self.id} ya está {self.status.value}"
            )
        self.status = IdempotencyStatus.COMPLETED
        self.result_reference = result_reference
        self.completed_at = _utcnow()

    def fail(self) -> None:
        if self.status != IdempotencyStatus.PENDING:
            raise IdempotencyRecordAlreadyFinalizedError(
                f"BusinessOperationIdempotencyRecord {self.id} ya está {self.status.value}"
            )
        self.status = IdempotencyStatus.FAILED
        self.completed_at = _utcnow()
