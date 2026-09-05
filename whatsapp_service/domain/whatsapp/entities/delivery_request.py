# domain/whatsapp/entities/delivery_request.py — WA-13
"""
DeliveryRequest — registro conversacional de "el cliente pidió programar
entrega a domicilio para el pedido X, con esta dirección". No es la orden
de entrega operativa (eso lo posee Orders/Delivery, vía
`DeliveryApiClient.schedule`, WA-9, que ya escribe `ventas.direccion_entrega`/
`fecha_entrega_programada`) — es, igual que `OrderDraft` (WA-10) para
pedidos, el rastro del canal de qué se solicitó y si el ERP lo aceptó,
con idempotencia de negocio propia (§19): pedir "programa mi entrega" dos
veces con la misma dirección no debe generar dos llamadas al ERP.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from domain.whatsapp._ids import new_id
from domain.whatsapp.enums import TERMINAL_DELIVERY_REQUEST_STATUSES, DeliveryRequestStatus
from domain.whatsapp.exceptions import WhatsAppDomainError


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DeliveryRequestAlreadyFinalizedError(WhatsAppDomainError):
    """La solicitud ya está SCHEDULED/FAILED — no se puede volver a
    resolver in-place (una reprogramación real es una solicitud nueva)."""


@dataclass
class DeliveryRequest:
    id: str
    conversation_id: str
    order_external_id: str
    address: str
    delivery_date: str
    customer_phone: str
    status: DeliveryRequestStatus
    failure_reason: Optional[str]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def start(
        cls, *, conversation_id: str, order_external_id: str, address: str,
        delivery_date: str = "", customer_phone: str = "",
    ) -> "DeliveryRequest":
        if not conversation_id:
            raise ValueError("conversation_id es obligatorio")
        if not order_external_id:
            raise ValueError("order_external_id es obligatorio")
        if not address.strip():
            raise ValueError("address es obligatorio — no se programa entrega sin dirección")
        now = _utcnow()
        return cls(
            id=new_id(),
            conversation_id=conversation_id,
            order_external_id=order_external_id,
            address=address.strip(),
            delivery_date=delivery_date,
            customer_phone=customer_phone,
            status=DeliveryRequestStatus.REQUESTED,
            failure_reason=None,
            created_at=now,
            updated_at=now,
        )

    def is_terminal(self) -> bool:
        return self.status in TERMINAL_DELIVERY_REQUEST_STATUSES

    def mark_scheduled(self) -> None:
        if self.is_terminal():
            raise DeliveryRequestAlreadyFinalizedError(
                f"DeliveryRequest {self.id} ya está {self.status.value}"
            )
        self.status = DeliveryRequestStatus.SCHEDULED
        self.updated_at = _utcnow()

    def mark_failed(self, reason: str) -> None:
        if self.is_terminal():
            raise DeliveryRequestAlreadyFinalizedError(
                f"DeliveryRequest {self.id} ya está {self.status.value}"
            )
        self.status = DeliveryRequestStatus.FAILED
        self.failure_reason = reason
        self.updated_at = _utcnow()
