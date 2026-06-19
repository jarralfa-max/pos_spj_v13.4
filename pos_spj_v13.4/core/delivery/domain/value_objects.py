"""Delivery domain value objects and enumerations.

Backend canonical types — all labels visible to users live in UNIT_LABELS_ES
and STATUS_LABELS_ES dictionaries, never hardcoded in UI.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum


# ── Existing value objects (preserved) ───────────────────────────────────────

@dataclass(frozen=True, slots=True)
class Quantity:
    value: Decimal
    unit: str = "u"

    def __init__(self, value: float | int | str | Decimal, unit: str = "u") -> None:
        decimal_value = Decimal(str(value or 0))
        if decimal_value < 0:
            raise ValueError("La cantidad delivery no puede ser negativa.")
        object.__setattr__(self, "value", decimal_value)
        object.__setattr__(self, "unit", (unit or "u").strip().lower())

    def as_float(self) -> float:
        return float(self.value)


@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal

    def __init__(self, amount: float | int | str | Decimal) -> None:
        quantized = Decimal(str(amount or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        object.__setattr__(self, "amount", quantized)

    def as_float(self) -> float:
        return float(self.amount)


@dataclass(frozen=True, slots=True)
class GeoPoint:
    lat: float
    lng: float

    def __post_init__(self) -> None:
        if not -90 <= float(self.lat) <= 90:
            raise ValueError("Latitud delivery fuera de rango.")
        if not -180 <= float(self.lng) <= 180:
            raise ValueError("Longitud delivery fuera de rango.")


# ── New domain enums ──────────────────────────────────────────────────────────

class DeliveryStatus(str, Enum):
    PENDING = "pending"
    PREPARING = "preparing"
    READY_FOR_PICKUP = "ready_for_pickup"
    READY_FOR_DISPATCH = "ready_for_dispatch"
    ASSIGNED = "assigned"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class FulfillmentType(str, Enum):
    PICKUP = "pickup"      # mostrador / counter
    DELIVERY = "delivery"  # domicilio


class PaymentStatus(str, Enum):
    PENDING = "pending"
    PAID = "paid"
    PARTIAL = "partial"


class UnitCode(str, Enum):
    KILOGRAM = "kg"
    GRAM = "g"
    PIECE = "piece"
    UNIT = "unit"
    BOX = "box"
    PACK = "pack"
    LITER = "liter"


class DeliveryAction(str, Enum):
    START_PREPARATION = "start_preparation"
    ADJUST_ITEM = "adjust_item"
    CONFIRM_PREPARATION = "confirm_preparation"
    ASSIGN_DRIVER = "assign_driver"
    START_ROUTE = "start_route"
    COMPLETE_DELIVERY = "complete_delivery"
    SEND_PAYMENT_LINK = "send_payment_link"
    CANCEL = "cancel"
    VIEW_DETAIL = "view_detail"
    PRINT_TICKET = "print_ticket"
    RESEND_RECEIPT = "resend_receipt"


# ── Unit categorisation ───────────────────────────────────────────────────────

WEIGHABLE_UNITS: frozenset[UnitCode] = frozenset({
    UnitCode.KILOGRAM,
    UnitCode.GRAM,
    UnitCode.LITER,
})

COUNTABLE_UNITS: frozenset[UnitCode] = frozenset({
    UnitCode.PIECE,
    UnitCode.UNIT,
    UnitCode.BOX,
    UnitCode.PACK,
})


# ── Spanish label maps (single source of truth) ───────────────────────────────

UNIT_LABELS_ES: dict[UnitCode, str] = {
    UnitCode.KILOGRAM: "kg",
    UnitCode.GRAM: "g",
    UnitCode.PIECE: "pza",
    UnitCode.UNIT: "unidad",
    UnitCode.BOX: "caja",
    UnitCode.PACK: "paquete",
    UnitCode.LITER: "L",
}

STATUS_LABELS_ES: dict[DeliveryStatus, str] = {
    DeliveryStatus.PENDING: "Pendiente",
    DeliveryStatus.PREPARING: "Preparación",
    DeliveryStatus.READY_FOR_PICKUP: "Listo para entregar",
    DeliveryStatus.READY_FOR_DISPATCH: "Listo para enviar",
    DeliveryStatus.ASSIGNED: "Repartidor asignado",
    DeliveryStatus.IN_TRANSIT: "En ruta",
    DeliveryStatus.DELIVERED: "Entregado",
    DeliveryStatus.CANCELLED: "Cancelado",
}


# ── Legacy string mappings (used by QueryService, not DB) ─────────────────────

LEGACY_STATUS_MAP: dict[str, DeliveryStatus] = {
    "pendiente": DeliveryStatus.PENDING,
    "preparacion": DeliveryStatus.PREPARING,
    "en_ruta": DeliveryStatus.IN_TRANSIT,
    "entregado": DeliveryStatus.DELIVERED,
    "cancelado": DeliveryStatus.CANCELLED,
    "listo_entrega": DeliveryStatus.READY_FOR_PICKUP,
    "listo_envio": DeliveryStatus.READY_FOR_DISPATCH,
    "asignado": DeliveryStatus.ASSIGNED,
}

LEGACY_UNIT_MAP: dict[str, UnitCode] = {
    "kg": UnitCode.KILOGRAM,
    "kilogramo": UnitCode.KILOGRAM,
    "kilo": UnitCode.KILOGRAM,
    "g": UnitCode.GRAM,
    "gramo": UnitCode.GRAM,
    "gr": UnitCode.GRAM,
    "pza": UnitCode.PIECE,
    "pieza": UnitCode.PIECE,
    "pz": UnitCode.PIECE,
    "u": UnitCode.UNIT,
    "unidad": UnitCode.UNIT,
    "l": UnitCode.LITER,
    "lt": UnitCode.LITER,
    "litro": UnitCode.LITER,
    "caja": UnitCode.BOX,
    "paquete": UnitCode.PACK,
    "paq": UnitCode.PACK,
}
