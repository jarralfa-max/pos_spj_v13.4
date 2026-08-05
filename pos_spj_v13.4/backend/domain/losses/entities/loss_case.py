"""LossCase aggregate root and protected workflow."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.losses.entities._validation import optional_uuid, required_uuid
from backend.domain.losses.entities.loss_line import LossLine
from backend.domain.losses.enums import LossClassificationCode, LossOrigin, LossStatus
from backend.domain.losses.exceptions import LossInvariantError, LossStateTransitionError


@dataclass
class LossCase:
    id: str
    operation_id: str
    branch_id: str
    warehouse_id: str
    reported_by_user_id: str
    classification: LossClassificationCode
    origin: LossOrigin
    reason_id: str
    status: LossStatus = LossStatus.DRAFT
    source_document_id: str | None = None
    notes: str = ""
    lines: list[LossLine] = field(default_factory=list)
    reviewed_by_user_id: str | None = None
    approved_by_user_id: str | None = None
    inventory_movement_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        for name in ("id", "operation_id", "branch_id", "warehouse_id",
                     "reported_by_user_id", "reason_id"):
            setattr(self, name, required_uuid(getattr(self, name), name))
        self.source_document_id = optional_uuid(self.source_document_id, "source_document_id")
        if self.id == self.operation_id:
            raise LossInvariantError("entity_id y operation_id deben ser distintos")
        if not isinstance(self.classification, LossClassificationCode):
            raise LossInvariantError("Clasificación canónica requerida")
        if not isinstance(self.origin, LossOrigin):
            raise LossInvariantError("Origen canónico requerido")
        if self.status is not LossStatus.DRAFT:
            raise LossInvariantError("Un LossCase nuevo debe iniciar en DRAFT")

    def _require_status(self, *allowed: LossStatus) -> None:
        if self.status not in allowed:
            expected = ", ".join(item.value for item in allowed)
            raise LossStateTransitionError(
                f"Transición inválida desde {self.status.value}; se esperaba {expected}")

    def add_line(self, line: LossLine) -> None:
        self._require_status(LossStatus.DRAFT)
        if any(existing.id == line.id for existing in self.lines):
            raise LossInvariantError("La línea ya pertenece al expediente")
        self.lines.append(line)

    def submit(self, *, actor_user_id: str) -> None:
        self._require_status(LossStatus.DRAFT)
        required_uuid(actor_user_id, "actor_user_id")
        if not self.lines:
            raise LossInvariantError("El expediente requiere al menos una línea")
        self.status = LossStatus.SUBMITTED

    def start_review(self, *, actor_user_id: str) -> None:
        self._require_status(LossStatus.SUBMITTED)
        self.reviewed_by_user_id = required_uuid(actor_user_id, "reviewed_by_user_id")
        self.status = LossStatus.UNDER_REVIEW

    def approve(self, *, actor_user_id: str) -> None:
        self._require_status(LossStatus.UNDER_REVIEW)
        actor = required_uuid(actor_user_id, "approved_by_user_id")
        if actor == self.reported_by_user_id:
            raise LossInvariantError("El reportante no puede aprobar su propia pérdida")
        self.approved_by_user_id = actor
        self.status = LossStatus.APPROVED

    def reject(self, *, actor_user_id: str) -> None:
        self._require_status(LossStatus.SUBMITTED, LossStatus.UNDER_REVIEW)
        self.reviewed_by_user_id = required_uuid(actor_user_id, "reviewed_by_user_id")
        self.status = LossStatus.REJECTED

    def mark_inventory_posted(self, *, movement_id: str) -> None:
        self._require_status(LossStatus.APPROVED)
        self.inventory_movement_id = required_uuid(movement_id, "inventory_movement_id")
        self.status = LossStatus.INVENTORY_POSTED

    def close(self, *, actor_user_id: str) -> None:
        self._require_status(LossStatus.INVENTORY_POSTED, LossStatus.REJECTED)
        required_uuid(actor_user_id, "actor_user_id")
        self.status = LossStatus.CLOSED

    @property
    def gross_value(self):
        return sum((line.gross_value for line in self.lines), start=Decimal("0"))

    @property
    def net_loss_value(self):
        return sum((line.net_loss_value for line in self.lines), start=Decimal("0"))
