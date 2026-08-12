"""ProcessingOrder aggregate root and protected workflow (§12, §13)."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.meat_processing.entities._validation import (
    decimal_value,
    optional_uuid,
    required_uuid,
)
from backend.domain.meat_processing.enums import ProcessingOrderStatus, ProcessType
from backend.domain.meat_processing.exceptions import (
    MeatProcessingInvariantError,
    MeatProcessingSegregationOfDutiesError,
    MeatProcessingStateTransitionError,
)

_TERMINAL = (ProcessingOrderStatus.CANCELLED, ProcessingOrderStatus.REVERSED)


@dataclass
class ProcessingOrder:
    id: str
    operation_id: str
    branch_id: str
    warehouse_id: str
    process_type: ProcessType
    target_product_id: str
    created_by_user_id: str
    planned_quantity: Decimal = Decimal("0")
    planned_weight: Decimal = Decimal("0")
    production_area_id: str | None = None
    work_center_id: str | None = None
    recipe_version_id: str | None = None
    cutting_scheme_version_id: str | None = None
    yield_profile_version_id: str | None = None
    source_type: str | None = None
    source_reference_id: str | None = None
    scheduled_start_at: datetime | None = None
    scheduled_end_at: datetime | None = None
    priority: int = 0
    status: ProcessingOrderStatus = ProcessingOrderStatus.DRAFT
    approved_by_user_id: str | None = None
    released_by_user_id: str | None = None
    started_by_user_id: str | None = None
    completed_by_user_id: str | None = None
    closed_by_user_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        for name in ("id", "operation_id", "branch_id", "warehouse_id",
                     "target_product_id", "created_by_user_id"):
            setattr(self, name, required_uuid(getattr(self, name), name))
        for name in ("production_area_id", "work_center_id", "recipe_version_id",
                     "cutting_scheme_version_id", "yield_profile_version_id",
                     "source_reference_id", "approved_by_user_id",
                     "released_by_user_id", "started_by_user_id",
                     "completed_by_user_id", "closed_by_user_id"):
            setattr(self, name, optional_uuid(getattr(self, name), name))
        for name in ("planned_quantity", "planned_weight"):
            setattr(self, name, decimal_value(getattr(self, name), name))
        if self.id == self.operation_id:
            raise MeatProcessingInvariantError("entity_id y operation_id deben ser distintos")
        if not isinstance(self.process_type, ProcessType):
            raise MeatProcessingInvariantError("Tipo de proceso canónico requerido")
        if self.planned_quantity < 0 or self.planned_weight < 0:
            raise MeatProcessingInvariantError("Cantidad y peso planeados no pueden ser negativos")
        if self.planned_quantity == 0 and self.planned_weight == 0:
            raise MeatProcessingInvariantError("La orden requiere cantidad o peso planeado positivo")

    def _require_status(self, *allowed: ProcessingOrderStatus) -> None:
        if self.status not in allowed:
            expected = ", ".join(item.value for item in allowed)
            raise MeatProcessingStateTransitionError(
                f"Transición inválida desde {self.status.value}; se esperaba {expected}")

    def submit_for_approval(self) -> None:
        self._require_status(ProcessingOrderStatus.DRAFT)
        self.status = ProcessingOrderStatus.PENDING_APPROVAL

    def approve(self, *, actor_user_id: str) -> None:
        self._require_status(ProcessingOrderStatus.PENDING_APPROVAL)
        actor = required_uuid(actor_user_id, "approved_by_user_id")
        if actor == self.created_by_user_id:
            raise MeatProcessingSegregationOfDutiesError(
                "Quien crea una orden elevada no debe aprobarla")
        self.approved_by_user_id = actor
        self.status = ProcessingOrderStatus.APPROVED

    def mark_materials_pending(self) -> None:
        self._require_status(ProcessingOrderStatus.APPROVED)
        self.status = ProcessingOrderStatus.MATERIALS_PENDING

    def mark_ready(self) -> None:
        self._require_status(ProcessingOrderStatus.APPROVED,
                              ProcessingOrderStatus.MATERIALS_PENDING)
        self.status = ProcessingOrderStatus.READY

    def apply_recipe_snapshot(
        self,
        *,
        recipe_version_id: str | None = None,
        cutting_scheme_version_id: str | None = None,
        yield_profile_version_id: str | None = None,
    ) -> None:
        """§14: captured once, right before release; immutable afterwards — a
        later active-version change in Products must never alter an order
        already in flight."""
        self._require_status(ProcessingOrderStatus.APPROVED, ProcessingOrderStatus.READY)
        if (self.recipe_version_id is not None or self.cutting_scheme_version_id is not None
                or self.yield_profile_version_id is not None):
            raise MeatProcessingInvariantError(
                "El snapshot de receta ya fue capturado; es inmutable")
        self.recipe_version_id = optional_uuid(recipe_version_id, "recipe_version_id")
        self.cutting_scheme_version_id = optional_uuid(
            cutting_scheme_version_id, "cutting_scheme_version_id")
        self.yield_profile_version_id = optional_uuid(
            yield_profile_version_id, "yield_profile_version_id")

    def release(self, *, actor_user_id: str) -> None:
        self._require_status(ProcessingOrderStatus.APPROVED, ProcessingOrderStatus.READY)
        self.released_by_user_id = required_uuid(actor_user_id, "released_by_user_id")
        self.status = ProcessingOrderStatus.RELEASED

    def start(self, *, actor_user_id: str) -> None:
        self._require_status(ProcessingOrderStatus.RELEASED)
        self.started_by_user_id = required_uuid(actor_user_id, "started_by_user_id")
        self.status = ProcessingOrderStatus.IN_PROGRESS

    def pause(self) -> None:
        self._require_status(ProcessingOrderStatus.IN_PROGRESS)
        self.status = ProcessingOrderStatus.PAUSED

    def resume(self) -> None:
        self._require_status(ProcessingOrderStatus.PAUSED)
        self.status = ProcessingOrderStatus.IN_PROGRESS

    def request_quality_review(self) -> None:
        self._require_status(ProcessingOrderStatus.IN_PROGRESS,
                              ProcessingOrderStatus.PARTIALLY_COMPLETED)
        self.status = ProcessingOrderStatus.PENDING_QUALITY

    def request_yield_reconciliation(self) -> None:
        self._require_status(ProcessingOrderStatus.IN_PROGRESS,
                              ProcessingOrderStatus.PARTIALLY_COMPLETED,
                              ProcessingOrderStatus.PENDING_QUALITY)
        self.status = ProcessingOrderStatus.PENDING_RECONCILIATION

    def partially_complete(self) -> None:
        self._require_status(ProcessingOrderStatus.IN_PROGRESS,
                              ProcessingOrderStatus.PENDING_QUALITY,
                              ProcessingOrderStatus.PENDING_RECONCILIATION)
        self.status = ProcessingOrderStatus.PARTIALLY_COMPLETED

    def complete(self, *, actor_user_id: str) -> None:
        self._require_status(ProcessingOrderStatus.IN_PROGRESS,
                              ProcessingOrderStatus.PARTIALLY_COMPLETED,
                              ProcessingOrderStatus.PENDING_QUALITY,
                              ProcessingOrderStatus.PENDING_RECONCILIATION)
        self.completed_by_user_id = required_uuid(actor_user_id, "completed_by_user_id")
        self.status = ProcessingOrderStatus.COMPLETED

    def close(self, *, actor_user_id: str) -> None:
        """Terminal, immutable per §13/§35. The caller (a future CloseProcessingOrder
        use case) is responsible for verifying consumptions/outputs/quality/yield
        preconditions are satisfied before invoking this — see OrderClosingPolicy."""
        self._require_status(ProcessingOrderStatus.COMPLETED)
        self.closed_by_user_id = required_uuid(actor_user_id, "closed_by_user_id")
        self.status = ProcessingOrderStatus.CLOSED

    def cancel(self) -> None:
        self._require_status(ProcessingOrderStatus.DRAFT,
                              ProcessingOrderStatus.PENDING_APPROVAL,
                              ProcessingOrderStatus.APPROVED,
                              ProcessingOrderStatus.MATERIALS_PENDING,
                              ProcessingOrderStatus.READY)
        self.status = ProcessingOrderStatus.CANCELLED

    def reverse(self, *, actor_user_id: str) -> None:
        self._require_status(ProcessingOrderStatus.CLOSED)
        required_uuid(actor_user_id, "reversed_by_user_id")
        if actor_user_id == self.closed_by_user_id:
            raise MeatProcessingSegregationOfDutiesError(
                "Quien revierte una orden debe tener autorización independiente")
        self.status = ProcessingOrderStatus.REVERSED

    @property
    def is_terminal(self) -> bool:
        return self.status in _TERMINAL or self.status == ProcessingOrderStatus.CLOSED
