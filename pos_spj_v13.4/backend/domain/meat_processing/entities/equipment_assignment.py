"""EquipmentAssignment (§19). Structural twin of OperatorAssignment (§32) —
tracks which equipment is in use by which order, for how long, without
turning equipment status itself into a scheduling engine."""

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.meat_processing.entities._validation import required_uuid
from backend.domain.meat_processing.exceptions import (
    MeatProcessingInvariantError,
    MeatProcessingStateTransitionError,
)


@dataclass
class EquipmentAssignment:
    id: str
    operation_id: str
    processing_order_id: str
    equipment_id: str
    assigned_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    released_at: datetime | None = None

    def __post_init__(self) -> None:
        for name in ("id", "operation_id", "processing_order_id", "equipment_id"):
            setattr(self, name, required_uuid(getattr(self, name), name))
        if self.id == self.operation_id:
            raise MeatProcessingInvariantError("entity_id y operation_id deben ser distintos")

    @property
    def is_active(self) -> bool:
        return self.released_at is None

    def release(self, *, released_at: datetime | None = None) -> None:
        if self.released_at is not None:
            raise MeatProcessingStateTransitionError("La asignación ya fue liberada")
        self.released_at = released_at or datetime.now(timezone.utc)
