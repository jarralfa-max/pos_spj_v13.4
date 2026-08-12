"""ProcessingBatch entity — a productive lot within a ProcessingOrder (§19).

Modeled as its own aggregate (not a list embedded in ProcessingOrder): §19 requires
one-to-one, one-to-many, many-to-one and controlled many-to-many cardinality between
orders and batches, which rules out a fixed embedded collection.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.meat_processing.entities._validation import (
    decimal_value,
    optional_uuid,
    required_uuid,
)
from backend.domain.meat_processing.enums import ProcessingBatchStatus
from backend.domain.meat_processing.exceptions import (
    MeatProcessingInvariantError,
    MeatProcessingStateTransitionError,
)


@dataclass
class ProcessingBatch:
    id: str
    operation_id: str
    processing_order_id: str
    batch_number: str
    source_lot_ids: tuple[str, ...] = ()
    planned_quantity: Decimal = Decimal("0")
    planned_weight: Decimal = Decimal("0")
    actual_quantity: Decimal = Decimal("0")
    actual_weight: Decimal = Decimal("0")
    status: ProcessingBatchStatus = ProcessingBatchStatus.PLANNED
    target_lot_code: str | None = None
    inventory_lot_id: str | None = None
    quality_status: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        for name in ("id", "operation_id", "processing_order_id"):
            setattr(self, name, required_uuid(getattr(self, name), name))
        self.source_lot_ids = tuple(
            required_uuid(lot_id, "source_lot_id") for lot_id in self.source_lot_ids)
        self.inventory_lot_id = optional_uuid(self.inventory_lot_id, "inventory_lot_id")
        for name in ("planned_quantity", "planned_weight", "actual_quantity", "actual_weight"):
            setattr(self, name, decimal_value(getattr(self, name), name))
        if self.id == self.operation_id:
            raise MeatProcessingInvariantError("entity_id y operation_id deben ser distintos")
        if not str(self.batch_number or "").strip():
            raise MeatProcessingInvariantError("batch_number es requerido")
        if self.planned_quantity < 0 or self.planned_weight < 0:
            raise MeatProcessingInvariantError("Cantidad y peso planeados no pueden ser negativos")
        if self.actual_quantity < 0 or self.actual_weight < 0:
            raise MeatProcessingInvariantError("Cantidad y peso reales no pueden ser negativos")

    def _require_status(self, *allowed: ProcessingBatchStatus) -> None:
        if self.status not in allowed:
            expected = ", ".join(item.value for item in allowed)
            raise MeatProcessingStateTransitionError(
                f"Transición inválida desde {self.status.value}; se esperaba {expected}")

    def start(self, *, started_at: datetime | None = None) -> None:
        self._require_status(ProcessingBatchStatus.PLANNED)
        self.status = ProcessingBatchStatus.IN_PROGRESS
        self.started_at = started_at or datetime.now(timezone.utc)

    def record_actuals(self, *, actual_quantity: Decimal, actual_weight: Decimal) -> None:
        self._require_status(ProcessingBatchStatus.IN_PROGRESS)
        self.actual_quantity = decimal_value(actual_quantity, "actual_quantity")
        self.actual_weight = decimal_value(actual_weight, "actual_weight")
        if self.actual_quantity < 0 or self.actual_weight < 0:
            raise MeatProcessingInvariantError("Cantidad y peso reales no pueden ser negativos")

    def complete(self, *, completed_at: datetime | None = None) -> None:
        self._require_status(ProcessingBatchStatus.IN_PROGRESS)
        self.status = ProcessingBatchStatus.COMPLETED
        self.completed_at = completed_at or datetime.now(timezone.utc)

    def cancel(self) -> None:
        self._require_status(ProcessingBatchStatus.PLANNED, ProcessingBatchStatus.IN_PROGRESS)
        self.status = ProcessingBatchStatus.CANCELLED

    def assign_inventory_lot(self, *, inventory_lot_id: str) -> None:
        self.inventory_lot_id = required_uuid(inventory_lot_id, "inventory_lot_id")
