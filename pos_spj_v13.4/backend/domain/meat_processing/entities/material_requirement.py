"""MaterialRequirement entity (§16). Distinguishes requerido / reservado /
asignado / consumido — each stage accumulates against the previous one, never
exceeding it. Procesamiento tracks this locally; the actual reservation lives
in Inventory (§39) — a future MaterialAvailabilityPort integration drives
`reserve()`/`allocate()` from real availability, not invented here.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.meat_processing.entities._validation import decimal_value, required_uuid
from backend.domain.meat_processing.enums import MaterialRequirementStatus
from backend.domain.meat_processing.exceptions import (
    MeatProcessingInvariantError,
    MeatProcessingStateTransitionError,
)

_CANCELLABLE = (MaterialRequirementStatus.REQUIRED, MaterialRequirementStatus.RESERVED,
                MaterialRequirementStatus.ALLOCATED)


@dataclass
class MaterialRequirement:
    id: str
    operation_id: str
    processing_order_id: str
    product_id: str
    required_quantity: Decimal = Decimal("0")
    required_weight: Decimal = Decimal("0")
    unit: str = "unit"
    substitution_allowed: bool = False
    quality_required: bool = False
    lot_required: bool = False
    status: MaterialRequirementStatus = MaterialRequirementStatus.REQUIRED
    reserved_quantity: Decimal = Decimal("0")
    reserved_weight: Decimal = Decimal("0")
    allocated_quantity: Decimal = Decimal("0")
    allocated_weight: Decimal = Decimal("0")
    consumed_quantity: Decimal = Decimal("0")
    consumed_weight: Decimal = Decimal("0")
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        for name in ("id", "operation_id", "processing_order_id", "product_id"):
            setattr(self, name, required_uuid(getattr(self, name), name))
        if self.id == self.operation_id:
            raise MeatProcessingInvariantError("entity_id y operation_id deben ser distintos")
        for name in ("required_quantity", "required_weight", "reserved_quantity",
                     "reserved_weight", "allocated_quantity", "allocated_weight",
                     "consumed_quantity", "consumed_weight"):
            setattr(self, name, decimal_value(getattr(self, name), name))
        if self.required_quantity < 0 or self.required_weight < 0:
            raise MeatProcessingInvariantError("Cantidad y peso requeridos no pueden ser negativos")
        if self.required_quantity == 0 and self.required_weight == 0:
            raise MeatProcessingInvariantError("El requerimiento necesita cantidad o peso positivo")
        if not str(self.unit or "").strip():
            raise MeatProcessingInvariantError("La unidad es requerida")

    def _require_status(self, *allowed: MaterialRequirementStatus) -> None:
        if self.status not in allowed:
            expected = ", ".join(item.value for item in allowed)
            raise MeatProcessingStateTransitionError(
                f"Transición inválida desde {self.status.value}; se esperaba {expected}")

    def reserve(self, *, quantity: Decimal = Decimal("0"), weight: Decimal = Decimal("0")) -> None:
        self._require_status(MaterialRequirementStatus.REQUIRED, MaterialRequirementStatus.RESERVED)
        qty, wt = decimal_value(quantity, "quantity"), decimal_value(weight, "weight")
        if self.reserved_quantity + qty > self.required_quantity:
            raise MeatProcessingInvariantError("La reserva excede la cantidad requerida")
        if self.reserved_weight + wt > self.required_weight:
            raise MeatProcessingInvariantError("La reserva excede el peso requerido")
        self.reserved_quantity += qty
        self.reserved_weight += wt
        self.status = MaterialRequirementStatus.RESERVED

    def allocate(self, *, quantity: Decimal = Decimal("0"), weight: Decimal = Decimal("0")) -> None:
        self._require_status(MaterialRequirementStatus.RESERVED, MaterialRequirementStatus.ALLOCATED)
        qty, wt = decimal_value(quantity, "quantity"), decimal_value(weight, "weight")
        if self.allocated_quantity + qty > self.reserved_quantity:
            raise MeatProcessingInvariantError("La asignación excede la cantidad reservada")
        if self.allocated_weight + wt > self.reserved_weight:
            raise MeatProcessingInvariantError("La asignación excede el peso reservado")
        self.allocated_quantity += qty
        self.allocated_weight += wt
        self.status = MaterialRequirementStatus.ALLOCATED

    def consume(self, *, quantity: Decimal = Decimal("0"), weight: Decimal = Decimal("0")) -> None:
        self._require_status(MaterialRequirementStatus.ALLOCATED, MaterialRequirementStatus.CONSUMED)
        qty, wt = decimal_value(quantity, "quantity"), decimal_value(weight, "weight")
        if self.consumed_quantity + qty > self.allocated_quantity:
            raise MeatProcessingInvariantError("El consumo excede la cantidad asignada")
        if self.consumed_weight + wt > self.allocated_weight:
            raise MeatProcessingInvariantError("El consumo excede el peso asignado")
        self.consumed_quantity += qty
        self.consumed_weight += wt
        self.status = MaterialRequirementStatus.CONSUMED

    def cancel(self) -> None:
        self._require_status(*_CANCELLABLE)
        self.status = MaterialRequirementStatus.CANCELLED

    @property
    def is_fully_reserved(self) -> bool:
        qty_done = self.required_quantity == 0 or self.reserved_quantity >= self.required_quantity
        wt_done = self.required_weight == 0 or self.reserved_weight >= self.required_weight
        return qty_done and wt_done
