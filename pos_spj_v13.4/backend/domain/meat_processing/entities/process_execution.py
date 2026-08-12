"""ProcessExecution entity — start/pause/resume/complete tracking (§20)."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.meat_processing.entities._validation import (
    decimal_value,
    optional_uuid,
    required_uuid,
)
from backend.domain.meat_processing.enums import ExecutionStatus
from backend.domain.meat_processing.exceptions import (
    MeatProcessingInvariantError,
    MeatProcessingStateTransitionError,
)


@dataclass
class ProcessExecution:
    id: str
    operation_id: str
    processing_order_id: str
    processing_batch_id: str | None = None
    work_center_id: str | None = None
    status: ExecutionStatus = ExecutionStatus.NOT_STARTED
    started_at: datetime | None = None
    paused_at: datetime | None = None
    resumed_at: datetime | None = None
    completed_at: datetime | None = None
    total_paused_seconds: Decimal = Decimal("0")
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        for name in ("id", "operation_id", "processing_order_id"):
            setattr(self, name, required_uuid(getattr(self, name), name))
        for name in ("processing_batch_id", "work_center_id"):
            setattr(self, name, optional_uuid(getattr(self, name), name))
        self.total_paused_seconds = decimal_value(
            self.total_paused_seconds, "total_paused_seconds")
        if self.id == self.operation_id:
            raise MeatProcessingInvariantError("entity_id y operation_id deben ser distintos")
        if self.total_paused_seconds < 0:
            raise MeatProcessingInvariantError("total_paused_seconds no puede ser negativo")

    def _require_status(self, *allowed: ExecutionStatus) -> None:
        if self.status not in allowed:
            expected = ", ".join(item.value for item in allowed)
            raise MeatProcessingStateTransitionError(
                f"Transición inválida desde {self.status.value}; se esperaba {expected}")

    def start(self, *, started_at: datetime | None = None) -> None:
        self._require_status(ExecutionStatus.NOT_STARTED)
        self.status = ExecutionStatus.ACTIVE
        self.started_at = started_at or datetime.now(timezone.utc)

    def pause(self, *, paused_at: datetime | None = None) -> None:
        self._require_status(ExecutionStatus.ACTIVE)
        self.status = ExecutionStatus.PAUSED
        self.paused_at = paused_at or datetime.now(timezone.utc)

    def resume(self, *, resumed_at: datetime | None = None) -> None:
        self._require_status(ExecutionStatus.PAUSED)
        moment = resumed_at or datetime.now(timezone.utc)
        if self.paused_at is not None:
            elapsed = Decimal(str((moment - self.paused_at).total_seconds()))
            self.total_paused_seconds += elapsed
        self.status = ExecutionStatus.ACTIVE
        self.resumed_at = moment

    def complete(self, *, completed_at: datetime | None = None) -> None:
        self._require_status(ExecutionStatus.ACTIVE)
        self.status = ExecutionStatus.COMPLETED
        self.completed_at = completed_at or datetime.now(timezone.utc)

    def cancel(self) -> None:
        self._require_status(ExecutionStatus.NOT_STARTED, ExecutionStatus.ACTIVE,
                              ExecutionStatus.PAUSED)
        self.status = ExecutionStatus.CANCELLED

    def fail(self) -> None:
        self._require_status(ExecutionStatus.ACTIVE, ExecutionStatus.PAUSED)
        self.status = ExecutionStatus.FAILED

    @property
    def duration_seconds(self) -> Decimal | None:
        if self.started_at is None:
            return None
        end = self.completed_at or datetime.now(timezone.utc)
        elapsed = Decimal(str((end - self.started_at).total_seconds()))
        return elapsed - self.total_paused_seconds
