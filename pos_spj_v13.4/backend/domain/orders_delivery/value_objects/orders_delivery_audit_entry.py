"""OrdersDeliveryAuditEntry — one auditable Pedidos/Delivery action (master
prompt §73: creación, confirmación, programación, activación, reserva,
liberación, preparación, peso, ajuste, aprobación del cliente, sustitución,
empaque, asignación, ruta, despacho, llegada, entrega, evidencia, falla,
reentrega, retorno, cancelación, reverso, cobro, liquidación, notificación,
WhatsApp, configuración).

Pure value object; persistence is
``backend/application/orders_delivery/audit.py``. Mirrors
``backend/domain/loyalty/value_objects/loyalty_audit_entry.py`` exactly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from backend.domain.orders_delivery.exceptions import InvalidOrdersDeliveryAuditFieldError


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class OrdersDeliveryAuditEntry:
    user_id: str
    operation_id: str
    action: str
    branch_id: str
    authorized_by: str | None = None
    entity_id: str | None = None
    before: Mapping[str, Any] = field(default_factory=dict)
    after: Mapping[str, Any] = field(default_factory=dict)
    reason: str | None = None
    device_id: str | None = None
    occurred_at: str = field(default_factory=_utcnow_iso)

    def __post_init__(self) -> None:
        if not self.user_id:
            raise InvalidOrdersDeliveryAuditFieldError("user_id requerido")
        if not self.operation_id:
            raise InvalidOrdersDeliveryAuditFieldError("operation_id requerido")
        if not self.action:
            raise InvalidOrdersDeliveryAuditFieldError("action requerido")
        if not self.branch_id:
            raise InvalidOrdersDeliveryAuditFieldError("branch_id requerido")
