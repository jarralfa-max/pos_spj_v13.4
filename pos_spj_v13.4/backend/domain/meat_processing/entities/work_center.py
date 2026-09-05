"""WorkCenter (§19/§33). Belongs to a ProductionArea; carries the capacity
figure `CapacityValidationService` (PROC-5) always takes as a caller-supplied
argument rather than a hardcoded constant — a WorkCenter row is where that
number now actually lives."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from backend.domain.meat_processing.entities._validation import decimal_value, required_uuid
from backend.domain.meat_processing.exceptions import MeatProcessingInvariantError

CapacityBasis = Literal["quantity", "weight"]


@dataclass
class WorkCenter:
    id: str
    production_area_id: str
    code: str
    name: str
    capacity_per_hour: Decimal = Decimal("0")
    capacity_basis: CapacityBasis = "weight"
    is_active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        for name in ("id", "production_area_id"):
            setattr(self, name, required_uuid(getattr(self, name), name))
        if not str(self.code or "").strip():
            raise MeatProcessingInvariantError("code es requerido")
        if not str(self.name or "").strip():
            raise MeatProcessingInvariantError("name es requerido")
        self.capacity_per_hour = decimal_value(self.capacity_per_hour, "capacity_per_hour")
        if self.capacity_per_hour < 0:
            raise MeatProcessingInvariantError("capacity_per_hour no puede ser negativo")
        if self.capacity_basis not in ("quantity", "weight"):
            raise MeatProcessingInvariantError("capacity_basis debe ser 'quantity' o 'weight'")

    def deactivate(self) -> None:
        self.is_active = False

    def activate(self) -> None:
        self.is_active = True
