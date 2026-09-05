"""ProcessIncident entity (§30). An incident *can* pause the order, block
outputs, open maintenance, open a loss case, request quality or raise an
alert — this entity only tracks its own lifecycle; those cross-module effects
are orchestrated by the application layer (PROC-8's ReportProcessIncidentUseCase
optionally pauses the order; the rest — maintenance/loss/quality/alerts — are
later integration phases, PROC-15/16/20)."""

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.meat_processing.entities._validation import optional_uuid, required_uuid
from backend.domain.meat_processing.enums import IncidentStatus, IncidentType
from backend.domain.meat_processing.exceptions import (
    MeatProcessingInvariantError,
    MeatProcessingStateTransitionError,
)


@dataclass
class ProcessIncident:
    id: str
    operation_id: str
    processing_order_id: str
    incident_type: IncidentType
    reported_by_user_id: str
    description: str
    process_execution_id: str | None = None
    status: IncidentStatus = IncidentStatus.OPEN
    reported_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_by_user_id: str | None = None
    resolved_at: datetime | None = None
    resolution_notes: str = ""

    def __post_init__(self) -> None:
        for name in ("id", "operation_id", "processing_order_id", "reported_by_user_id"):
            setattr(self, name, required_uuid(getattr(self, name), name))
        self.process_execution_id = optional_uuid(self.process_execution_id, "process_execution_id")
        self.resolved_by_user_id = optional_uuid(self.resolved_by_user_id, "resolved_by_user_id")
        if self.id == self.operation_id:
            raise MeatProcessingInvariantError("entity_id y operation_id deben ser distintos")
        if not isinstance(self.incident_type, IncidentType):
            raise MeatProcessingInvariantError("Tipo de incidencia canónico requerido")
        if not str(self.description or "").strip():
            raise MeatProcessingInvariantError("La incidencia requiere una descripción")

    def _require_status(self, *allowed: IncidentStatus) -> None:
        if self.status not in allowed:
            expected = ", ".join(item.value for item in allowed)
            raise MeatProcessingStateTransitionError(
                f"Transición inválida desde {self.status.value}; se esperaba {expected}")

    def start_review(self) -> None:
        self._require_status(IncidentStatus.OPEN)
        self.status = IncidentStatus.UNDER_REVIEW

    def resolve(self, *, actor_user_id: str, resolution_notes: str = "") -> None:
        self._require_status(IncidentStatus.OPEN, IncidentStatus.UNDER_REVIEW)
        self.resolved_by_user_id = required_uuid(actor_user_id, "resolved_by_user_id")
        self.resolution_notes = resolution_notes
        self.resolved_at = datetime.now(timezone.utc)
        self.status = IncidentStatus.RESOLVED

    def close(self) -> None:
        self._require_status(IncidentStatus.RESOLVED)
        self.status = IncidentStatus.CLOSED
