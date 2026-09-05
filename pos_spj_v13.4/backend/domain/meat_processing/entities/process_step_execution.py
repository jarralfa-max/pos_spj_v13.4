"""ProcessStepExecution entity (§20/§8). A named sub-step within a
ProcessExecution (e.g. "deshuesado", "empacado") — simpler than the parent
execution (no pause/resume; steps are short, atomic units of work)."""

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.meat_processing.entities._validation import required_uuid
from backend.domain.meat_processing.enums import ExecutionStatus
from backend.domain.meat_processing.exceptions import (
    MeatProcessingInvariantError,
    MeatProcessingStateTransitionError,
)


@dataclass
class ProcessStepExecution:
    id: str
    operation_id: str
    process_execution_id: str
    step_name: str
    sequence: int = 0
    status: ExecutionStatus = ExecutionStatus.NOT_STARTED
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        for name in ("id", "operation_id", "process_execution_id"):
            setattr(self, name, required_uuid(getattr(self, name), name))
        if self.id == self.operation_id:
            raise MeatProcessingInvariantError("entity_id y operation_id deben ser distintos")
        if not str(self.step_name or "").strip():
            raise MeatProcessingInvariantError("step_name es requerido")
        if self.sequence < 0:
            raise MeatProcessingInvariantError("sequence no puede ser negativo")

    def _require_status(self, *allowed: ExecutionStatus) -> None:
        if self.status not in allowed:
            expected = ", ".join(item.value for item in allowed)
            raise MeatProcessingStateTransitionError(
                f"Transición inválida desde {self.status.value}; se esperaba {expected}")

    def start(self, *, started_at: datetime | None = None) -> None:
        self._require_status(ExecutionStatus.NOT_STARTED)
        self.status = ExecutionStatus.ACTIVE
        self.started_at = started_at or datetime.now(timezone.utc)

    def complete(self, *, completed_at: datetime | None = None) -> None:
        self._require_status(ExecutionStatus.ACTIVE)
        self.status = ExecutionStatus.COMPLETED
        self.completed_at = completed_at or datetime.now(timezone.utc)

    def cancel(self) -> None:
        self._require_status(ExecutionStatus.NOT_STARTED, ExecutionStatus.ACTIVE)
        self.status = ExecutionStatus.CANCELLED
