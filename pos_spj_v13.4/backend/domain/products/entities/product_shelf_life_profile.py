"""ProductShelfLifeProfile — declared shelf life and freshness gates (§19).

Products defines the numbers (never hardcoded in the UI). Receiving and sale gates
(minimum remaining days) let Compras/POS reject stock too close to expiry.
Day counts are non-negative integers; the profile carries a validity window.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.domain.products.exceptions import InvalidShelfLifeProfileError
from backend.shared.ids import new_uuid


def _days(value, label: str) -> int:
    if isinstance(value, bool):
        raise InvalidShelfLifeProfileError(f"{label} inválido")
    try:
        d = int(value)
    except (TypeError, ValueError) as exc:
        raise InvalidShelfLifeProfileError(f"{label} debe ser entero") from exc
    if d < 0:
        raise InvalidShelfLifeProfileError(f"{label} no puede ser negativo")
    return d


@dataclass
class ProductShelfLifeProfile:
    product_id: str
    shelf_life_days: int
    id: str = field(default_factory=new_uuid)
    minimum_remaining_for_receipt: int = 0
    minimum_remaining_for_sale: int = 0
    storage_condition: str = "AMBIENT"        # AMBIENT | CHILLED | FROZEN
    opened_shelf_life_days: int = 0
    frozen_shelf_life_days: int = 0
    thawed_shelf_life_days: int = 0
    effective_from: str | None = None
    effective_to: str | None = None

    def __post_init__(self) -> None:
        if not self.product_id:
            raise InvalidShelfLifeProfileError("El perfil requiere producto")
        self.shelf_life_days = _days(self.shelf_life_days, "shelf_life_days")
        if self.shelf_life_days <= 0:
            raise InvalidShelfLifeProfileError("shelf_life_days debe ser positivo")
        self.minimum_remaining_for_receipt = _days(
            self.minimum_remaining_for_receipt, "minimum_remaining_for_receipt")
        self.minimum_remaining_for_sale = _days(
            self.minimum_remaining_for_sale, "minimum_remaining_for_sale")
        self.opened_shelf_life_days = _days(self.opened_shelf_life_days, "opened_shelf_life_days")
        self.frozen_shelf_life_days = _days(self.frozen_shelf_life_days, "frozen_shelf_life_days")
        self.thawed_shelf_life_days = _days(self.thawed_shelf_life_days, "thawed_shelf_life_days")
        if self.minimum_remaining_for_receipt > self.shelf_life_days:
            raise InvalidShelfLifeProfileError(
                "El mínimo para recepción no puede exceder la vida útil total")

    def accepts_on_receipt(self, remaining_days: int) -> bool:
        return int(remaining_days) >= self.minimum_remaining_for_receipt

    def sellable_with_remaining(self, remaining_days: int) -> bool:
        return int(remaining_days) >= self.minimum_remaining_for_sale
