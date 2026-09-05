"""ReworkOrder entity (§29). "No modificar silenciosamente la orden
original" — a ReworkOrder never touches the source ProcessingOrder or its
blocked ProcessOutput; it links to a *new* ProcessingOrder
(`source_type="REWORK_ORDER"`, `source_reference_id=<rework_order.id>`,
mirroring PROC-5's plan→order linkage) that actually executes the rework
through the same núcleo productivo — no parallel execution mechanism (§1).
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.meat_processing.entities._validation import (
    decimal_value,
    optional_uuid,
    required_uuid,
)
from backend.domain.meat_processing.enums import ReworkOrderStatus, ReworkOrigin
from backend.domain.meat_processing.exceptions import (
    MeatProcessingInvariantError,
    MeatProcessingSegregationOfDutiesError,
    MeatProcessingStateTransitionError,
)


@dataclass
class ReworkOrder:
    id: str
    operation_id: str
    source_output_id: str
    product_id: str
    origin: ReworkOrigin
    created_by_user_id: str
    quantity: Decimal = Decimal("0")
    weight: Decimal = Decimal("0")
    reason: str = ""
    status: ReworkOrderStatus = ReworkOrderStatus.CREATED
    approved_by_user_id: str | None = None
    processing_order_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        for name in ("id", "operation_id", "source_output_id", "product_id",
                     "created_by_user_id"):
            setattr(self, name, required_uuid(getattr(self, name), name))
        for name in ("approved_by_user_id", "processing_order_id"):
            setattr(self, name, optional_uuid(getattr(self, name), name))
        for name in ("quantity", "weight"):
            setattr(self, name, decimal_value(getattr(self, name), name))
        if self.id == self.operation_id:
            raise MeatProcessingInvariantError("entity_id y operation_id deben ser distintos")
        if not isinstance(self.origin, ReworkOrigin):
            raise MeatProcessingInvariantError("Origen de reproceso canónico requerido")
        if self.quantity < 0 or self.weight < 0:
            raise MeatProcessingInvariantError("Cantidad y peso no pueden ser negativos")
        if self.quantity == 0 and self.weight == 0:
            raise MeatProcessingInvariantError("El reproceso requiere cantidad o peso positivo")

    def _require_status(self, *allowed: ReworkOrderStatus) -> None:
        if self.status not in allowed:
            expected = ", ".join(item.value for item in allowed)
            raise MeatProcessingStateTransitionError(
                f"Transición inválida desde {self.status.value}; se esperaba {expected}")

    def approve(self, *, actor_user_id: str) -> None:
        self._require_status(ReworkOrderStatus.CREATED)
        actor = required_uuid(actor_user_id, "approved_by_user_id")
        if actor == self.created_by_user_id:
            raise MeatProcessingSegregationOfDutiesError(
                "Quien crea un reproceso no debe aprobarlo")
        self.approved_by_user_id = actor
        self.status = ReworkOrderStatus.APPROVED

    def start_execution(self, *, processing_order_id: str) -> None:
        self._require_status(ReworkOrderStatus.APPROVED)
        self.processing_order_id = required_uuid(processing_order_id, "processing_order_id")
        self.status = ReworkOrderStatus.IN_PROGRESS

    def complete(self) -> None:
        self._require_status(ReworkOrderStatus.IN_PROGRESS)
        self.status = ReworkOrderStatus.COMPLETED

    def close(self) -> None:
        self._require_status(ReworkOrderStatus.COMPLETED)
        self.status = ReworkOrderStatus.CLOSED

    def cancel(self) -> None:
        self._require_status(ReworkOrderStatus.CREATED, ReworkOrderStatus.APPROVED)
        self.status = ReworkOrderStatus.CANCELLED
