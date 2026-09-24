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


#: Canales de venta en los que una lista de CANAL puede regir. Son los códigos
#: con los que Ventas (`POS`) y Pedidos/Delivery (`OrderChannel`) piden precio:
#: el motor compara el canal de la lista contra ÉSE código, así que un texto
#: libre ("whats", "Mostrador") nunca coincidía con nada. Una prueba de
#: arquitectura verifica que cada código exista en `OrderChannel`.
SALE_CHANNELS = ("POS", "WHATSAPP", "COUNTER", "PHONE", "E_COMMERCE", "SALES_REP",
                 "BACKOFFICE")


def normalize_channel(value) -> str | None:
    """Código canónico de canal (mayúsculas, sin espacios) o `None` si vacío."""
    texto = str(value or "").strip().upper()
    return texto or None


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
