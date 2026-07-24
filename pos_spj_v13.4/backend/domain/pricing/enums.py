"""Canonical enums for the pricing / costing bounded context (PRC-2)."""

from __future__ import annotations

from enum import Enum


class PriceListStatus(str, Enum):
    DRAFT = "DRAFT"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class PriceListKind(str, Enum):
    BASE = "BASE"                 # precio base del producto
    CHANNEL = "CHANNEL"           # por canal (POS/e-commerce/…)
    CUSTOMER = "CUSTOMER"         # lista de cliente
    PROMOTIONAL = "PROMOTIONAL"


class CostMethod(str, Enum):
    AVERAGE = "AVERAGE"           # costo promedio ponderado
    LAST = "LAST"                 # último costo
    STANDARD = "STANDARD"         # costo estándar


class PriceSource(str, Enum):
    """De dónde salió el precio resuelto (prioridad de resolución)."""

    VOLUME = "VOLUME"
    CUSTOMER_LIST = "CUSTOMER_LIST"
    LIST = "LIST"
    BASE = "BASE"
    NONE = "NONE"


IMMUTABLE_LIST_STATES = frozenset({
    PriceListStatus.APPROVED, PriceListStatus.ACTIVE,
})
