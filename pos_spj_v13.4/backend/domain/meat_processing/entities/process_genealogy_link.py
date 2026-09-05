"""ProcessGenealogyLink entity (§38). An immutable edge in the traceability
graph: `(upstream_entity_type, upstream_entity_id) → (downstream_entity_type,
downstream_entity_id)` — e.g. a ProcessOutput consumed as a MaterialConsumption
by another order (PROC-12's `ChainOutputAsConsumptionUseCase`). Within a single
order, consumption and output already share `processing_order_id`, so an
explicit link is only needed to make a *cross-order* chain queryable — that's
what "multinivel" genealogy actually requires (§38: upstream/downstream/recall).
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.meat_processing.entities._validation import (
    decimal_value,
    optional_uuid,
    required_uuid,
)
from backend.domain.meat_processing.exceptions import MeatProcessingInvariantError


@dataclass
class ProcessGenealogyLink:
    id: str
    operation_id: str
    upstream_entity_type: str
    upstream_entity_id: str
    downstream_entity_type: str
    downstream_entity_id: str
    product_id: str
    linked_by_user_id: str
    lot_id: str | None = None
    quantity: Decimal = Decimal("0")
    weight: Decimal = Decimal("0")
    linked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        for name in ("id", "operation_id", "upstream_entity_id", "downstream_entity_id",
                     "product_id", "linked_by_user_id"):
            setattr(self, name, required_uuid(getattr(self, name), name))
        self.lot_id = optional_uuid(self.lot_id, "lot_id")
        for name in ("quantity", "weight"):
            setattr(self, name, decimal_value(getattr(self, name), name))
        if self.id == self.operation_id:
            raise MeatProcessingInvariantError("entity_id y operation_id deben ser distintos")
        if not str(self.upstream_entity_type or "").strip():
            raise MeatProcessingInvariantError("upstream_entity_type es requerido")
        if not str(self.downstream_entity_type or "").strip():
            raise MeatProcessingInvariantError("downstream_entity_type es requerido")
        if (self.upstream_entity_type == self.downstream_entity_type
                and self.upstream_entity_id == self.downstream_entity_id):
            raise MeatProcessingInvariantError("Un enlace no puede apuntar a sí mismo")
        if self.quantity < 0 or self.weight < 0:
            raise MeatProcessingInvariantError("Cantidad y peso no pueden ser negativos")
