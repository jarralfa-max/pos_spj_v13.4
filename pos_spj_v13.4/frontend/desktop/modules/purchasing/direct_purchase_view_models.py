"""Display view models and mappers for the direct-purchase UI (es-MX).

A cart line lives here as an immutable VM; totals are recomputed by the presenter
from Decimal, never in the widget.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from frontend.desktop.formatters import format_money

STATUS_ES = {
    "DRAFT": "Borrador", "PENDING_AUTHORIZATION": "Pendiente de autorización",
    "CONFIRMED": "Confirmada", "PARTIALLY_RECEIVED": "Recibida parcial",
    "RECEIVED": "Recibida", "CANCELLED": "Cancelada", "REVERSED": "Reversada",
}
STATUS_VARIANT = {
    "DRAFT": "neutral", "PENDING_AUTHORIZATION": "warning", "CONFIRMED": "primary",
    "PARTIALLY_RECEIVED": "warning", "RECEIVED": "success", "CANCELLED": "neutral",
    "REVERSED": "danger",
}
PAYMENT_CONDITION_ES = {
    "IMMEDIATE_PAYMENT": "Pago inmediato", "SUPPLIER_CREDIT": "Crédito de proveedor",
    "ADVANCE_PAYMENT": "Anticipo", "MIXED": "Mixto",
    "PAYMENT_INSTRUCTION": "Instrucción de pago",
}
PAYMENT_SOURCE_ES = {
    "PETTY_CASH": "Caja chica", "TREASURY_ACCOUNT": "Cuenta de tesorería",
    "BANK_TRANSFER": "Transferencia bancaria", "AUTHORIZED_CARD": "Tarjeta autorizada",
    "MERCADO_PAGO": "Mercado Pago", "OTHER_CONFIGURED_SOURCE": "Otra fuente configurada",
}
#: payment sources the UI may offer — POS operative cash is deliberately absent.
PAYMENT_SOURCE_OPTIONS = [
    ("PETTY_CASH", "Caja chica"), ("TREASURY_ACCOUNT", "Cuenta de tesorería"),
    ("BANK_TRANSFER", "Transferencia bancaria"), ("AUTHORIZED_CARD", "Tarjeta autorizada"),
    ("MERCADO_PAGO", "Mercado Pago"),
]
PAYMENT_CONDITION_OPTIONS = [
    ("IMMEDIATE_PAYMENT", "Pago inmediato"), ("SUPPLIER_CREDIT", "Crédito de proveedor"),
    ("ADVANCE_PAYMENT", "Anticipo"),
]
MODE_OPTIONS = [
    ("DIRECT_WITH_IMMEDIATE_RECEIPT", "Con recepción inmediata"),
    ("DIRECT_WITH_PENDING_RECEIPT", "Con recepción pendiente"),
    ("DIRECT_SERVICE", "Servicio"), ("DIRECT_EXPENSE", "Gasto"),
]


def status_es(code: str | None) -> str:
    return STATUS_ES.get(str(code or ""), str(code or "—"))


def payment_condition_es(code: str | None) -> str:
    return PAYMENT_CONDITION_ES.get(str(code or ""), str(code or "—"))


def money(value) -> str:
    return format_money(value)


@dataclass
class CartLineVM:
    """A mutable cart line captured in the widget before persistence."""

    product_id: str
    description: str
    quantity: Decimal
    unit_cost: Decimal
    tax: Decimal = Decimal("0")
    discount: Decimal = Decimal("0")
    purchase_unit: str = "PZA"
    inventory_unit: str = "PZA"
    conversion_factor: Decimal = Decimal("1")
    is_weight: bool = False

    def line_subtotal(self) -> Decimal:
        return self.quantity * self.unit_cost

    def line_total(self) -> Decimal:
        return self.line_subtotal() - self.discount + self.tax

    def as_payload(self) -> dict:
        return {
            "product_id": self.product_id, "description": self.description,
            "quantity": str(self.quantity), "unit_cost": str(self.unit_cost),
            "tax": str(self.tax), "discount": str(self.discount),
            "purchase_unit": self.purchase_unit, "inventory_unit": self.inventory_unit,
            "conversion_factor": str(self.conversion_factor),
        }


@dataclass(frozen=True)
class TableViewModel:
    rows: list[list[str]] = field(default_factory=list)
    row_ids: list[str] = field(default_factory=list)
    total: int = 0
