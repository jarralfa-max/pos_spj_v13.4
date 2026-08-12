"""YieldReconciliation entity (§26).

Classification into WITHIN_TOLERANCE/WARNING/OUT_OF_TOLERANCE/CRITICAL is computed
by `YieldReconciliationPolicy.classify()` (a future use case's job — thresholds are
never hardcoded here, §26) and fed back in via `apply_classification()`. The entity
itself only tracks its own state, mirroring how LossCase never imports its own
policies.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.meat_processing.entities._validation import (
    decimal_value,
    optional_uuid,
    required_uuid,
)
from backend.domain.meat_processing.enums import YieldStatus
from backend.domain.meat_processing.exceptions import (
    MeatProcessingInvariantError,
    MeatProcessingStateTransitionError,
)

_CLASSIFIED = (YieldStatus.WITHIN_TOLERANCE, YieldStatus.WARNING,
               YieldStatus.OUT_OF_TOLERANCE, YieldStatus.CRITICAL)


@dataclass
class YieldReconciliation:
    id: str
    operation_id: str
    processing_order_id: str
    input_quantity: Decimal
    input_weight: Decimal
    expected_output_quantity: Decimal
    expected_output_weight: Decimal
    actual_output_quantity: Decimal
    actual_output_weight: Decimal
    tolerance_pct: Decimal
    processing_batch_id: str | None = None
    co_product_weight: Decimal = Decimal("0")
    by_product_weight: Decimal = Decimal("0")
    waste_weight: Decimal = Decimal("0")
    status: YieldStatus = YieldStatus.PENDING_REVIEW
    reviewed_by_user_id: str | None = None
    calculated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        for name in ("id", "operation_id", "processing_order_id"):
            setattr(self, name, required_uuid(getattr(self, name), name))
        self.processing_batch_id = optional_uuid(self.processing_batch_id, "processing_batch_id")
        self.reviewed_by_user_id = optional_uuid(self.reviewed_by_user_id, "reviewed_by_user_id")
        for name in ("input_quantity", "input_weight", "expected_output_quantity",
                     "expected_output_weight", "actual_output_quantity",
                     "actual_output_weight", "co_product_weight", "by_product_weight",
                     "waste_weight", "tolerance_pct"):
            setattr(self, name, decimal_value(getattr(self, name), name))
        if self.id == self.operation_id:
            raise MeatProcessingInvariantError("entity_id y operation_id deben ser distintos")
        for name in ("input_quantity", "input_weight", "expected_output_quantity",
                     "expected_output_weight", "actual_output_quantity",
                     "actual_output_weight", "co_product_weight", "by_product_weight",
                     "waste_weight"):
            if getattr(self, name) < 0:
                raise MeatProcessingInvariantError(f"{name} no puede ser negativo")
        if self.tolerance_pct < 0:
            raise MeatProcessingInvariantError("tolerance_pct no puede ser negativo")

    @property
    def variance_pct(self) -> Decimal | None:
        if self.expected_output_weight == 0:
            return None
        return ((self.actual_output_weight - self.expected_output_weight)
                / self.expected_output_weight) * Decimal("100")

    @property
    def unexplained_difference(self) -> Decimal:
        """Informational only — §26 explicitly forbids assuming outputs must sum
        to exactly 100% of input."""
        accounted = (self.actual_output_weight + self.co_product_weight
                     + self.by_product_weight + self.waste_weight)
        return self.input_weight - accounted

    def apply_classification(self, status: YieldStatus) -> None:
        if self.status is not YieldStatus.PENDING_REVIEW:
            raise MeatProcessingStateTransitionError(
                "Solo se puede clasificar un YieldReconciliation en PENDING_REVIEW")
        if status not in _CLASSIFIED:
            raise MeatProcessingInvariantError("Clasificación de rendimiento inválida")
        self.status = status

    def approve(self, *, actor_user_id: str) -> None:
        if self.status not in _CLASSIFIED:
            raise MeatProcessingStateTransitionError(
                "El rendimiento debe clasificarse antes de aprobarse")
        self.reviewed_by_user_id = required_uuid(actor_user_id, "reviewed_by_user_id")
        self.status = YieldStatus.APPROVED
