"""ProcessOutput entity (§22).

All output kinds (main product, co-product, by-product, WIP, reworkable, waste,
loss) share the exact same field shape, so they're modeled as one entity
discriminated by `OutputType` rather than one class per §8's `process_output.py` /
`process_by_product.py` / `process_subproduct.py` split — a literal class-per-type
split here would be pure duplication (see PROC-2 plan note).
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.meat_processing.entities._validation import (
    decimal_value,
    optional_uuid,
    required_uuid,
)
from backend.domain.meat_processing.enums import OutputQualityStatus, OutputType
from backend.domain.meat_processing.exceptions import MeatProcessingInvariantError


@dataclass
class ProcessOutput:
    id: str
    operation_id: str
    processing_order_id: str
    product_id: str
    warehouse_id: str
    captured_by_user_id: str
    output_type: OutputType
    processing_batch_id: str | None = None
    lot_id: str | None = None
    location_id: str | None = None
    quantity: Decimal = Decimal("0")
    weight: Decimal = Decimal("0")
    pieces: int | None = None
    unit: str = "unit"
    quality_status: OutputQualityStatus = OutputQualityStatus.PENDING_INSPECTION
    inventory_operation_id: str | None = None
    produced_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        for name in ("id", "operation_id", "processing_order_id", "product_id",
                     "warehouse_id", "captured_by_user_id"):
            setattr(self, name, required_uuid(getattr(self, name), name))
        for name in ("processing_batch_id", "lot_id", "location_id",
                     "inventory_operation_id"):
            setattr(self, name, optional_uuid(getattr(self, name), name))
        for name in ("quantity", "weight"):
            setattr(self, name, decimal_value(getattr(self, name), name))
        if self.id == self.operation_id:
            raise MeatProcessingInvariantError("entity_id y operation_id deben ser distintos")
        if not isinstance(self.output_type, OutputType):
            raise MeatProcessingInvariantError("Tipo de output canónico requerido")
        if not isinstance(self.quality_status, OutputQualityStatus):
            raise MeatProcessingInvariantError("Estado de calidad canónico requerido")
        if self.quantity < 0 or self.weight < 0:
            raise MeatProcessingInvariantError("Cantidad y peso no pueden ser negativos")
        if self.quantity == 0 and self.weight == 0:
            raise MeatProcessingInvariantError("El output requiere cantidad o peso positivo")
        if self.pieces is not None and self.pieces < 0:
            raise MeatProcessingInvariantError("Las piezas no pueden ser negativas")
        if not str(self.unit or "").strip():
            raise MeatProcessingInvariantError("La unidad es requerida")

    def mark_quality_status(self, status: OutputQualityStatus) -> None:
        """Dumb setter — Quality owns the actual liberate/block decision (§28);
        Processing only records what Quality decided."""
        if not isinstance(status, OutputQualityStatus):
            raise MeatProcessingInvariantError("Estado de calidad canónico requerido")
        self.quality_status = status

    def assign_inventory_operation(self, *, inventory_operation_id: str) -> None:
        self.inventory_operation_id = required_uuid(
            inventory_operation_id, "inventory_operation_id")

    @property
    def is_releasable_to_stock(self) -> bool:
        return self.quality_status == OutputQualityStatus.RELEASED
