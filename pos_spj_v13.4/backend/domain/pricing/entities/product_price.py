"""ProductPrice / VolumePrice — the sale price of a product in a list (PRC-2).

A ``ProductPrice`` binds a product (optionally a branch) to a ``Money`` sale price
within a price list, with an optional minimum price and validity window.
``VolumePrice`` adds quantity tiers (kg ≥ N → special price). Money-only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from backend.domain.pricing.exceptions import InvalidPriceListError
from backend.domain.pricing.value_objects.money import Money
from backend.shared.ids import new_uuid


def _validity_day(value, campo: str) -> date | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError as exc:
        raise InvalidPriceListError(
            f"Fecha de vigencia inválida en «{campo}»: {value!r} (use AAAA-MM-DD)") from exc


def validate_validity(effective_from, effective_to) -> None:
    """La vigencia de un precio: fechas AAAA-MM-DD y un fin que no preceda al
    inicio.

    Vivía sólo en el diálogo. El motor compara `substr(fecha, 1, 10)` como
    texto, así que una fecha mal escrita o invertida guardada por cualquier
    otra vía dejaba un precio que no rige NUNCA sin que nadie lo notara.
    """
    desde = _validity_day(effective_from, "vigente desde")
    hasta = _validity_day(effective_to, "vigente hasta")
    if desde is not None and hasta is not None and hasta < desde:
        raise InvalidPriceListError("La vigencia no puede terminar antes de empezar")


def _qty(value) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise InvalidPriceListError("min_quantity no puede ser float")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise InvalidPriceListError(f"Cantidad inválida: {value!r}") from exc


@dataclass
class ProductPrice:
    price_list_id: str
    product_id: str
    sale_price: Money
    id: str = field(default_factory=new_uuid)
    branch_id: str | None = None
    min_price: Money | None = None
    effective_from: str | None = None
    effective_to: str | None = None

    def __post_init__(self) -> None:
        if not self.price_list_id or not self.product_id:
            raise InvalidPriceListError("El precio requiere lista y producto")
        if not isinstance(self.sale_price, Money):
            raise InvalidPriceListError("sale_price debe ser Money")
        if self.min_price is not None:
            if not isinstance(self.min_price, Money):
                raise InvalidPriceListError("min_price debe ser Money")
            if self.sale_price < self.min_price:
                raise InvalidPriceListError(
                    "El precio de venta no puede ser menor al mínimo del propio precio")
        validate_validity(self.effective_from, self.effective_to)


@dataclass
class VolumePrice:
    product_price_id: str
    min_quantity: Decimal
    price: Money
    id: str = field(default_factory=new_uuid)

    def __post_init__(self) -> None:
        if not self.product_price_id:
            raise InvalidPriceListError("El precio por volumen requiere precio base")
        if not isinstance(self.price, Money):
            raise InvalidPriceListError("price debe ser Money")
        self.min_quantity = _qty(self.min_quantity)
        if self.min_quantity <= 0:
            raise InvalidPriceListError("min_quantity debe ser positiva")

    def applies_to(self, quantity) -> bool:
        return _qty(quantity) >= self.min_quantity
