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
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional, Union

from domain.whatsapp._ids import new_id
from domain.whatsapp.enums import TERMINAL_ORDER_DRAFT_STATUSES, DeliveryMethod, OrderDraftStatus
from domain.whatsapp.exceptions import WhatsAppDomainError


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


#: Lo que un llamador puede entregar como cantidad o precio. Los flujos
#: conversacionales parsean texto del usuario y las pruebas usan int/float por
#: comodidad, así que el borde acepta las tres formas y normaliza a Decimal.
Money = Union[Decimal, int, str, float]

_CENTS = Decimal("0.01")


def to_decimal(value: Money) -> Decimal:
    """Convierte a Decimal pasando SIEMPRE por str.

    `Decimal(0.1)` arrastra el error binario del float (0.1000000000000000055…);
    `Decimal(str(0.1))` da exactamente `0.1`. Este servicio recibe precios desde
    el catálogo del ERP y desde texto de WhatsApp, así que la conversión tiene
    que ser la segura aunque el llamador pase un float.
    """
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def quantize_money(value: Decimal) -> Decimal:
    """Redondea a dos decimales con HALF_UP.

    `round()` de Python usa banker's rounding (round-half-to-even), que reparte
    los .5 hacia el par más cercano; para importes se espera el redondeo
    comercial. La aritmética previa se mantiene en Decimal completo y sólo el
    resultado presentado se cuantiza.
    """
    return value.quantize(_CENTS, rounding=ROUND_HALF_UP)


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
    quantity: Decimal
    unit: str
    unit_price: Decimal

    @classmethod
    def create(
        cls, *, product_external_id: str, product_name: str,
        quantity: Money, unit: str, unit_price: Money,
    ) -> "OrderDraftLine":
        quantity = to_decimal(quantity)
        unit_price = to_decimal(unit_price)
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
    def subtotal(self) -> Decimal:
        return quantize_money(self.quantity * self.unit_price)


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
        self, *, product_external_id: str, product_name: str,
        quantity: Money, unit: str, unit_price: Money,
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
    def total(self) -> Decimal:
        return quantize_money(sum((line.subtotal for line in self.lines), Decimal("0")))

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
