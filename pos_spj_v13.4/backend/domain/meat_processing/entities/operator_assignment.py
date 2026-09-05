"""OperatorAssignment entity (§32). Does not replace RRHH/nómina — only tracks
who is assigned to which order, in which role, for the duration of the work."""

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.meat_processing.entities._validation import optional_uuid, required_uuid
from backend.domain.meat_processing.enums import OperatorRole
from backend.domain.meat_processing.exceptions import (
    MeatProcessingInvariantError,
    MeatProcessingStateTransitionError,
)


@dataclass
class OperatorAssignment:
    id: str
    operation_id: str
    processing_order_id: str
    user_id: str
    role_type: OperatorRole
    work_center_id: str | None = None
    assigned_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    released_at: datetime | None = None

    def __post_init__(self) -> None:
        for name in ("id", "operation_id", "processing_order_id", "user_id"):
            setattr(self, name, required_uuid(getattr(self, name), name))
        self.work_center_id = optional_uuid(self.work_center_id, "work_center_id")
        if self.id == self.operation_id:
            raise MeatProcessingInvariantError("entity_id y operation_id deben ser distintos")
        if not isinstance(self.role_type, OperatorRole):
            raise MeatProcessingInvariantError("Rol operativo canónico requerido")

    @property
    def is_active(self) -> bool:
        return self.released_at is None

    def release(self, *, released_at: datetime | None = None) -> None:
        if self.released_at is not None:
            raise MeatProcessingStateTransitionError("La asignación ya fue liberada")
        self.released_at = released_at or datetime.now(timezone.utc)
