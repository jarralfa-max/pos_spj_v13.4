"""Display view models and mappers for the direct-purchase UI (es-MX).

A cart line lives here as an immutable VM; totals are recomputed by the presenter
from Decimal, never in the widget.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from frontend.desktop.formatters import format_money
from frontend.desktop.modules.purchasing.enterprise_view_models import (
    DIRECT_PURCHASE_STATUS_ES,
    TableViewModel,
)

__all__ = ["CartLineVM", "ConfirmationSummaryVM", "TableViewModel", "error_text", "money",
           "payment_condition_es", "status_es"]

#: Una sola traducción para toda Compras (enterprise_view_models).
STATUS_ES = DIRECT_PURCHASE_STATUS_ES
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
#: Qué se compra (§11: no se mezcla con cómo llega).
KIND_OPTIONS = [("GOODS", "Mercancía"), ("DIRECT_SERVICE", "Servicio"),
                ("DIRECT_EXPENSE", "Gasto")]
#: Cómo llega la mercancía (§11).
FULFILLMENT_OPTIONS = [
    ("IMMEDIATE_RECEIPT", "Recepción inmediata"), ("LATER_RECEIPT", "Recepción posterior"),
    ("SUPPLIER_DELIVERY", "Entrega del proveedor"),
    ("SUPPLIER_PICKUP", "Recolección en proveedor"),
]
FULFILLMENT_ES = dict(FULFILLMENT_OPTIONS)
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


@dataclass(frozen=True)
class ConfirmationSummaryVM:
    """Resumen de una compra por confirmar, listo para mostrar (sin ids)."""

    direct_purchase_id: str
    document_number: str
    status: str
    supplier: str
    branch: str
    warehouse: str
    total: str
    payment_condition: str
    condition_label: str
    requires_payment_source: bool
    payment_sources: list = field(default_factory=list)


@dataclass
class CartLineVM:
    """A mutable cart line captured in the widget before persistence."""

    product_id: str
    description: str
    quantity: Decimal
    unit_cost: Decimal
    tax: Decimal = Decimal("0")
    discount: Decimal = Decimal("0")
    # Vacío = la unidad base del producto; la resuelve el caso de uso contra
    # Productos. La pantalla nunca inventa una unidad.
    purchase_unit: str = ""
    inventory_unit: str = ""
    conversion_factor: Decimal = Decimal("1")
    is_weight: bool = False
    # Peso variable (Productos): peso real pesado y si el costo es POR KILO.
    # El caso de uso vuelve a decidir la base con el maestro; esto sólo sirve
    # para que el total de la pantalla coincida con el que se guardará.
    net_weight: Decimal | None = None
    priced_by_weight: bool = False

    @property
    def cost_missing(self) -> bool:
        """Sin costo válido (el dominio exige costo > 0)."""
        return self.unit_cost is None or self.unit_cost <= 0

    def billable_quantity(self) -> Decimal:
        return self.net_weight if self.priced_by_weight and self.net_weight else self.quantity

    def line_subtotal(self) -> Decimal:
        return self.billable_quantity() * self.unit_cost

    def line_total(self) -> Decimal:
        return self.line_subtotal() - self.discount + self.tax

    def as_payload(self) -> dict:
        return {
            "product_id": self.product_id, "description": self.description,
            "quantity": str(self.quantity), "unit_cost": str(self.unit_cost),
            "tax": str(self.tax), "discount": str(self.discount),
            "purchase_unit": self.purchase_unit, "inventory_unit": self.inventory_unit,
            "conversion_factor": str(self.conversion_factor),
            "net_weight": str(self.net_weight) if self.net_weight else None,
        }



#: Mensajes para el usuario según el `error_code` del caso de uso. Los códigos
#: técnicos y los ids jamás se muestran; lo que no está aquí muestra el mensaje
#: en español que ya trae el caso de uso.
ERROR_TEXT_ES = {
    "SESSION_CONTEXT_REQUIRED": "Selecciona la sucursal y el almacén destino para continuar.",
    "WAREHOUSE_NOT_IN_BRANCH": ("El almacén elegido no pertenece a la sucursal o no admite "
                                "recepción de compras. Elige otro almacén."),
    "BRANCH_NOT_ALLOWED": "La sucursal elegida no tiene habilitada la compra directa.",
    "PAYMENT_NOT_BOOKABLE": ("La fuente de pago elegida no se puede contabilizar. Elige otra "
                             "fuente o pide a Finanzas que configure la cuenta."),
    "INVALID_PAYMENT_SOURCE": "Selecciona una fuente de pago válida.",
    "AUTHORIZATION_REQUIRED": ("La compra requiere autorización antes de confirmar. "
                               "Autorízala desde el Historial."),
    "PERMISSION_DENIED": "No tienes permiso para realizar esta acción.",
}


def error_text(message: str | None, data: dict | None = None) -> str:
    """Texto de error para mostrar: por código si se conoce; si no, el mensaje."""
    code = (data or {}).get("error_code")
    if code in ERROR_TEXT_ES:
        return ERROR_TEXT_ES[code]
    return str(message or "").strip() or "No se pudo completar la operación."


#: Compras busca en el catálogo GLOBAL; la habilitación por sucursal sólo se
#: INFORMA en el resultado (etiqueta corta + cómo habilitarlo en el tooltip).
DISABLED_IN_BRANCH_LABEL = "deshabilitado para esta sucursal"
DISABLED_IN_BRANCH_TOOLTIP = "Habilítalo en Productos → Sucursales y surtidos."


def product_search_option(option):
    """``ProcurementProductOption`` → ``SearchOption`` para los buscadores de
    Compras, marcando los productos no habilitados en la sucursal del formulario."""
    from frontend.desktop.components.search_selector import SearchOption
    if option.enabled_in_branch is False:
        subtitle = f"{option.code} · {DISABLED_IN_BRANCH_LABEL}" if option.code             else DISABLED_IN_BRANCH_LABEL
        return SearchOption(id=option.product_id, label=option.name, subtitle=subtitle,
                            tooltip=DISABLED_IN_BRANCH_TOOLTIP)
    return SearchOption(id=option.product_id, label=option.name, subtitle=option.code)
