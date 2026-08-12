"""MaterialConsumption entity (§17). Processing requests inventory movements; it
never posts them itself (§39) — `post()` only records that Inventory confirmed the
movement referenced by `inventory_operation_id`."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.meat_processing.entities._validation import (
    decimal_value,
    optional_uuid,
    required_uuid,
)
from backend.domain.meat_processing.enums import ConsumptionStatus
from backend.domain.meat_processing.exceptions import (
    MeatProcessingInvariantError,
    MeatProcessingStateTransitionError,
)


@dataclass
class MaterialConsumption:
    id: str
    operation_id: str
    processing_order_id: str
    product_id: str
    warehouse_id: str
    captured_by_user_id: str
    processing_batch_id: str | None = None
    lot_id: str | None = None
    location_id: str | None = None
    planned_quantity: Decimal = Decimal("0")
    planned_weight: Decimal = Decimal("0")
    actual_quantity: Decimal = Decimal("0")
    actual_weight: Decimal = Decimal("0")
    unit: str = "unit"
    weighing_id: str | None = None
    inventory_operation_id: str | None = None
    status: ConsumptionStatus = ConsumptionStatus.DRAFT
    consumed_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        for name in ("id", "operation_id", "processing_order_id", "product_id",
                     "warehouse_id", "captured_by_user_id"):
            setattr(self, name, required_uuid(getattr(self, name), name))
        for name in ("processing_batch_id", "lot_id", "location_id", "weighing_id",
                     "inventory_operation_id"):
            setattr(self, name, optional_uuid(getattr(self, name), name))
        for name in ("planned_quantity", "planned_weight", "actual_quantity", "actual_weight"):
            setattr(self, name, decimal_value(getattr(self, name), name))
        if self.id == self.operation_id:
            raise MeatProcessingInvariantError("entity_id y operation_id deben ser distintos")
        if self.planned_quantity < 0 or self.planned_weight < 0:
            raise MeatProcessingInvariantError("Cantidad y peso planeados no pueden ser negativos")
        if self.actual_quantity < 0 or self.actual_weight < 0:
            raise MeatProcessingInvariantError("Cantidad y peso reales no pueden ser negativos")
        if not str(self.unit or "").strip():
            raise MeatProcessingInvariantError("La unidad es requerida")

    def _require_status(self, *allowed: ConsumptionStatus) -> None:
        if self.status not in allowed:
            expected = ", ".join(item.value for item in allowed)
            raise MeatProcessingStateTransitionError(
                f"Transición inválida desde {self.status.value}; se esperaba {expected}")

    def record_actuals(self, *, actual_quantity: Decimal, actual_weight: Decimal,
                        consumed_at: datetime | None = None) -> None:
        self._require_status(ConsumptionStatus.DRAFT)
        self.actual_quantity = decimal_value(actual_quantity, "actual_quantity")
        self.actual_weight = decimal_value(actual_weight, "actual_weight")
        if self.actual_quantity < 0 or self.actual_weight < 0:
            raise MeatProcessingInvariantError("Cantidad y peso reales no pueden ser negativos")
        self.consumed_at = consumed_at or datetime.now(timezone.utc)
        self.status = ConsumptionStatus.PENDING_POSTING

    def post(self, *, inventory_operation_id: str) -> None:
        self._require_status(ConsumptionStatus.PENDING_POSTING)
        self.inventory_operation_id = required_uuid(
            inventory_operation_id, "inventory_operation_id")
        self.status = ConsumptionStatus.POSTED

    def reverse(self) -> None:
        self._require_status(ConsumptionStatus.POSTED)
        self.status = ConsumptionStatus.REVERSED
