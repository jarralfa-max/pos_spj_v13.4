# domain/whatsapp/entities/order_draft.py — WA-10 (§34-35 del prompt maestro)
"""
OrderDraft — el carrito conversacional que WhatsApp arma ANTES de pedirle
a Orders que cree el pedido canónico. §34 es explícito: "el draft
conversacional no es el pedido canónico" — este objeto vive y muere en el
canal; `OrdersApiClient.create()` (WA-9) es lo único que produce un pedido
real en el ERP.

Cantidades por peso (§35): `unit` refleja lo que ya trae `ProductRef`
(kg/pieza/paquete/...) — no se modela aquí el flujo completo de ajuste de
peso post-pesaje con aprobación del cliente (§36); eso es una extensión
futura sobre este mismo borrador, no construida en esta fase (nada en el
checklist explícito de WA-10 la pide todavía).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

from domain.whatsapp._ids import new_id
from domain.whatsapp.enums import TERMINAL_ORDER_DRAFT_STATUSES, DeliveryMethod, OrderDraftStatus
from domain.whatsapp.exceptions import WhatsAppDomainError


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EmptyOrderDraftError(WhatsAppDomainError):
    """No se puede confirmar un borrador sin líneas."""


class OrderDraftAlreadyFinalizedError(WhatsAppDomainError):
    """El borrador ya está CONFIRMED/CANCELLED — no se puede seguir
    editando ni volver a confirmar/cancelar."""


@dataclass
class OrderDraftLine:
    id: str
    product_external_id: str
    product_name: str
    quantity: float
    unit: str
    unit_price: float

    @classmethod
    def create(
        cls, *, product_external_id: str, product_name: str, quantity: float, unit: str, unit_price: float
    ) -> "OrderDraftLine":
        if quantity <= 0:
            raise ValueError("La cantidad debe ser mayor a cero")
        return cls(
            id=new_id(),
            product_external_id=product_external_id,
            product_name=product_name,
            quantity=quantity,
            unit=unit,
            unit_price=unit_price,
        )

    @property
    def subtotal(self) -> float:
        return round(self.quantity * self.unit_price, 2)


@dataclass
class OrderDraft:
    id: str
    conversation_id: str
    branch_id: Optional[str]
    customer_external_id: Optional[str]
    delivery_method: Optional[DeliveryMethod]
    status: OrderDraftStatus
    lines: List[OrderDraftLine]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def start(cls, *, conversation_id: str, branch_id: Optional[str] = None) -> "OrderDraft":
        if not conversation_id:
            raise ValueError("conversation_id es obligatorio")
        now = _utcnow()
        return cls(
            id=new_id(),
            conversation_id=conversation_id,
            branch_id=branch_id,
            customer_external_id=None,
            delivery_method=None,
            status=OrderDraftStatus.BUILDING,
            lines=[],
            created_at=now,
            updated_at=now,
        )

    def is_terminal(self) -> bool:
        return self.status in TERMINAL_ORDER_DRAFT_STATUSES

    def _assert_editable(self) -> None:
        if self.is_terminal():
            raise OrderDraftAlreadyFinalizedError(
                f"OrderDraft {self.id} ya está {self.status.value}; no se puede editar"
            )

    def add_line(
        self, *, product_external_id: str, product_name: str, quantity: float, unit: str, unit_price: float
    ) -> OrderDraftLine:
        self._assert_editable()
        line = OrderDraftLine.create(
            product_external_id=product_external_id, product_name=product_name,
            quantity=quantity, unit=unit, unit_price=unit_price,
        )
        self.lines.append(line)
        self.updated_at = _utcnow()
        return line

    def remove_line(self, line_id: str) -> None:
        self._assert_editable()
        self.lines = [line for line in self.lines if line.id != line_id]
        self.updated_at = _utcnow()

    def set_customer(self, customer_external_id: str) -> None:
        self._assert_editable()
        self.customer_external_id = customer_external_id
        self.updated_at = _utcnow()

    def set_delivery_method(self, method: DeliveryMethod) -> None:
        self._assert_editable()
        self.delivery_method = method
        self.updated_at = _utcnow()

    @property
    def total(self) -> float:
        return round(sum(line.subtotal for line in self.lines), 2)

    def request_confirmation(self) -> None:
        self._assert_editable()
        if not self.lines:
            raise EmptyOrderDraftError(f"OrderDraft {self.id} no tiene líneas")
        self.status = OrderDraftStatus.AWAITING_CONFIRMATION
        self.updated_at = _utcnow()

    def confirm(self) -> None:
        if self.status not in (OrderDraftStatus.BUILDING, OrderDraftStatus.AWAITING_CONFIRMATION):
            raise OrderDraftAlreadyFinalizedError(
                f"OrderDraft {self.id} está {self.status.value}; no se puede confirmar"
            )
        if not self.lines:
            raise EmptyOrderDraftError(f"OrderDraft {self.id} no tiene líneas")
        self.status = OrderDraftStatus.CONFIRMED
        self.updated_at = _utcnow()

    def cancel(self) -> None:
        self._assert_editable()
        self.status = OrderDraftStatus.CANCELLED
        self.updated_at = _utcnow()
