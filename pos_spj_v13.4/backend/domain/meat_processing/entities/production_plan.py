"""ProductionPlan aggregate root (§11). The plan never moves inventory — it
only expresses demand; PROC-6+ builds the use case that converts an approved
line into a real ProcessingOrder via `convert_line()`.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.meat_processing.entities._validation import required_uuid
from backend.domain.meat_processing.entities.production_plan_line import ProductionPlanLine
from backend.domain.meat_processing.enums import ProductionPlanStatus
from backend.domain.meat_processing.exceptions import (
    MeatProcessingInvariantError,
    MeatProcessingStateTransitionError,
)

_CANCELLABLE = (
    ProductionPlanStatus.DRAFT, ProductionPlanStatus.GENERATED,
    ProductionPlanStatus.UNDER_REVIEW, ProductionPlanStatus.APPROVED,
    ProductionPlanStatus.PARTIALLY_CONVERTED,
)
_CONVERTIBLE = (ProductionPlanStatus.APPROVED, ProductionPlanStatus.PARTIALLY_CONVERTED)


@dataclass
class ProductionPlan:
    id: str
    operation_id: str
    branch_id: str
    planning_period: str
    created_by_user_id: str
    status: ProductionPlanStatus = ProductionPlanStatus.DRAFT
    approved_by_user_id: str | None = None
    lines: list[ProductionPlanLine] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        for name in ("id", "operation_id", "branch_id", "created_by_user_id"):
            setattr(self, name, required_uuid(getattr(self, name), name))
        if self.approved_by_user_id is not None:
            self.approved_by_user_id = required_uuid(
                self.approved_by_user_id, "approved_by_user_id")
        if self.id == self.operation_id:
            raise MeatProcessingInvariantError("entity_id y operation_id deben ser distintos")
        if not str(self.planning_period or "").strip():
            raise MeatProcessingInvariantError("planning_period es requerido")

    def _require_status(self, *allowed: ProductionPlanStatus) -> None:
        if self.status not in allowed:
            expected = ", ".join(item.value for item in allowed)
            raise MeatProcessingStateTransitionError(
                f"Transición inválida desde {self.status.value}; se esperaba {expected}")

    def add_line(self, line: ProductionPlanLine) -> None:
        self._require_status(ProductionPlanStatus.DRAFT, ProductionPlanStatus.GENERATED)
        if any(existing.id == line.id for existing in self.lines):
            raise MeatProcessingInvariantError("La línea ya pertenece al plan")
        self.lines.append(line)

    def generate(self) -> None:
        self._require_status(ProductionPlanStatus.DRAFT)
        if not self.lines:
            raise MeatProcessingInvariantError("El plan requiere al menos una línea")
        self.status = ProductionPlanStatus.GENERATED

    def submit_for_review(self) -> None:
        self._require_status(ProductionPlanStatus.GENERATED)
        self.status = ProductionPlanStatus.UNDER_REVIEW

    def approve(self, *, actor_user_id: str) -> None:
        self._require_status(ProductionPlanStatus.UNDER_REVIEW)
        actor = required_uuid(actor_user_id, "approved_by_user_id")
        if actor == self.created_by_user_id:
            raise MeatProcessingInvariantError(
                "Quien crea un plan elevado no debe aprobarlo")
        self.approved_by_user_id = actor
        self.status = ProductionPlanStatus.APPROVED

    def cancel(self) -> None:
        self._require_status(*_CANCELLABLE)
        self.status = ProductionPlanStatus.CANCELLED

    def convert_line(self, line_id: str, *, processing_order_id: str,
                      converted_quantity: Decimal = Decimal("0"),
                      converted_weight: Decimal = Decimal("0")) -> None:
        self._require_status(*_CONVERTIBLE)
        line = next((item for item in self.lines if item.id == line_id), None)
        if line is None:
            raise MeatProcessingInvariantError(f"Línea no encontrada en el plan: {line_id}")
        line.record_conversion(
            processing_order_id=processing_order_id,
            converted_quantity=converted_quantity, converted_weight=converted_weight)
        self._recompute_conversion_status()

    def _recompute_conversion_status(self) -> None:
        if all(line.is_fully_converted for line in self.lines):
            self.status = ProductionPlanStatus.CONVERTED
        elif any(line.is_partially_converted or line.is_fully_converted for line in self.lines):
            self.status = ProductionPlanStatus.PARTIALLY_CONVERTED

    @property
    def is_fully_converted(self) -> bool:
        return bool(self.lines) and all(line.is_fully_converted for line in self.lines)
