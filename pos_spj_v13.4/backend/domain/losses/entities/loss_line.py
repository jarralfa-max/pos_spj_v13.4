"""A product/lot/quantity line affected by a loss case."""

from dataclasses import dataclass
from decimal import Decimal

from backend.domain.losses.entities._validation import decimal_value, optional_uuid, required_uuid
from backend.domain.losses.exceptions import LossInvariantError


@dataclass(frozen=True)
class LossLine:
    id: str
    product_id: str
    quantity: Decimal = Decimal("0")
    weight: Decimal = Decimal("0")
    unit: str = "unit"
    lot_id: str | None = None
    location_id: str | None = None
    unit_cost: Decimal = Decimal("0")
    recoverable_value: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", required_uuid(self.id, "loss_line_id"))
        object.__setattr__(self, "product_id", required_uuid(self.product_id, "product_id"))
        object.__setattr__(self, "lot_id", optional_uuid(self.lot_id, "lot_id"))
        object.__setattr__(self, "location_id", optional_uuid(self.location_id, "location_id"))
        for name in ("quantity", "weight", "unit_cost", "recoverable_value"):
            object.__setattr__(self, name, decimal_value(getattr(self, name), name))
        if self.quantity < 0 or self.weight < 0:
            raise LossInvariantError("Cantidad y peso no pueden ser negativos")
        if self.quantity == 0 and self.weight == 0:
            raise LossInvariantError("La línea requiere cantidad o peso positivo")
        if self.unit_cost < 0 or self.recoverable_value < 0:
            raise LossInvariantError("Costo y valor recuperable no pueden ser negativos")
        if not str(self.unit or "").strip():
            raise LossInvariantError("La unidad es requerida")

    @property
    def gross_value(self) -> Decimal:
        basis = self.weight if self.weight > 0 else self.quantity
        return basis * self.unit_cost

    @property
    def net_loss_value(self) -> Decimal:
        return max(Decimal("0"), self.gross_value - self.recoverable_value)
