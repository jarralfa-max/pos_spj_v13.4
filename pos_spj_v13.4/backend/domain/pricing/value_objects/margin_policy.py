"""MarginPolicy — the minimum-price / target-margin protection (PRC-2).

Products may declare a minimum sale price and/or a target margin. Selling below the
minimum requires a hot authorization (PRICING_PRICE_MIN_OVERRIDE). Pure value
object; Decimal/Money-only.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from backend.domain.pricing.exceptions import InvalidMarginPolicyError
from backend.domain.pricing.value_objects.money import Money


def _opt_pct(value) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool) or isinstance(value, float):
        raise InvalidMarginPolicyError("target_margin_pct no puede ser float")
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise InvalidMarginPolicyError(f"Margen inválido: {value!r}") from exc
    if not (Decimal("0") <= d <= Decimal("100")):
        raise InvalidMarginPolicyError("target_margin_pct debe estar en [0, 100]")
    return d


@dataclass(frozen=True)
class MarginPolicy:
    minimum_price: Money | None = None
    target_margin_pct: Decimal | None = None

    def __post_init__(self) -> None:
        if self.minimum_price is not None and not isinstance(self.minimum_price, Money):
            raise InvalidMarginPolicyError("minimum_price debe ser Money")
        object.__setattr__(self, "target_margin_pct", _opt_pct(self.target_margin_pct))

    def allows(self, price: Money) -> bool:
        """True si el precio respeta el precio mínimo (sin autorización)."""
        if self.minimum_price is None:
            return True
        return not (price < self.minimum_price)

    def target_price_from_cost(self, cost: Money) -> Money | None:
        """Precio sugerido para alcanzar el margen objetivo sobre el costo."""
        if self.target_margin_pct is None:
            return None
        divisor = Decimal("1") - (self.target_margin_pct / Decimal("100"))
        if divisor <= 0:
            return None
        return cost.multiply(Decimal("1") / divisor)
