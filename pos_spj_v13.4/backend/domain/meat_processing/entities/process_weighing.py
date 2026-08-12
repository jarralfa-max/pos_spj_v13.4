"""ProcessWeighing entity (§21).

The one cross-field invariant §21 calls out explicitly: a manual override requires
an authorizing user — "la captura manual fuera de tolerancia requiere permiso".
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.meat_processing.entities._validation import (
    decimal_value,
    optional_uuid,
    required_uuid,
)
from backend.domain.meat_processing.enums import WeighingType
from backend.domain.meat_processing.exceptions import MeatProcessingInvariantError


@dataclass
class ProcessWeighing:
    id: str
    operation_id: str
    processing_order_id: str
    captured_by_user_id: str
    weighing_type: WeighingType
    gross_weight: Decimal
    tare_weight: Decimal = Decimal("0")
    unit: str = "kg"
    processing_batch_id: str | None = None
    scale_id: str | None = None
    stable: bool = True
    manual_override: bool = False
    authorized_by_user_id: str | None = None
    source_reference: str | None = None
    captured_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        for name in ("id", "operation_id", "processing_order_id", "captured_by_user_id"):
            setattr(self, name, required_uuid(getattr(self, name), name))
        for name in ("processing_batch_id", "scale_id", "authorized_by_user_id"):
            setattr(self, name, optional_uuid(getattr(self, name), name))
        for name in ("gross_weight", "tare_weight"):
            setattr(self, name, decimal_value(getattr(self, name), name))
        if self.id == self.operation_id:
            raise MeatProcessingInvariantError("entity_id y operation_id deben ser distintos")
        if not isinstance(self.weighing_type, WeighingType):
            raise MeatProcessingInvariantError("Tipo de pesaje canónico requerido")
        if self.gross_weight < 0 or self.tare_weight < 0:
            raise MeatProcessingInvariantError("El peso bruto y la tara no pueden ser negativos")
        if self.tare_weight > self.gross_weight:
            raise MeatProcessingInvariantError("La tara no puede exceder el peso bruto")
        if not self.stable and not self.manual_override:
            raise MeatProcessingInvariantError(
                "No se acepta un peso inestable sin captura manual autorizada")
        if self.manual_override and self.authorized_by_user_id is None:
            raise MeatProcessingInvariantError(
                "La captura manual fuera de tolerancia requiere autorización")
        if not str(self.unit or "").strip():
            raise MeatProcessingInvariantError("La unidad es requerida")

    @property
    def net_weight(self) -> Decimal:
        return self.gross_weight - self.tare_weight
