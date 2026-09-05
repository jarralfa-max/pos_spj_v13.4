"""PackagingExecution entity (§25). An immutable capture record — like
ProcessWeighing, packaging is a fact once recorded, not a workflow with
states. Printing (ProductionLabel) is tracked separately: "la impresión no
determina el éxito productivo" — a packaging execution is complete and valid
whether or not its label has printed yet.
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
class PackagingExecution:
    id: str
    operation_id: str
    processing_order_id: str
    product_id: str
    packaging_material_id: str
    package_quantity: int
    net_weight: Decimal
    gross_weight: Decimal
    packaged_by_user_id: str
    tare_weight: Decimal = Decimal("0")
    lot_id: str | None = None
    process_output_id: str | None = None
    production_date: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expiration_date: datetime | None = None
    packaged_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        for name in ("id", "operation_id", "processing_order_id", "product_id",
                     "packaging_material_id", "packaged_by_user_id"):
            setattr(self, name, required_uuid(getattr(self, name), name))
        for name in ("lot_id", "process_output_id"):
            setattr(self, name, optional_uuid(getattr(self, name), name))
        self.net_weight = decimal_value(self.net_weight, "net_weight")
        self.gross_weight = decimal_value(self.gross_weight, "gross_weight")
        self.tare_weight = decimal_value(self.tare_weight, "tare_weight")
        if self.id == self.operation_id:
            raise MeatProcessingInvariantError("entity_id y operation_id deben ser distintos")
        if self.package_quantity <= 0:
            raise MeatProcessingInvariantError("package_quantity debe ser positivo")
        if self.net_weight <= 0 or self.gross_weight <= 0:
            raise MeatProcessingInvariantError("El peso neto y bruto deben ser positivos")
        if self.tare_weight < 0:
            raise MeatProcessingInvariantError("La tara no puede ser negativa")
        if self.tare_weight > self.gross_weight:
            raise MeatProcessingInvariantError("La tara no puede exceder el peso bruto")
        if self.net_weight > self.gross_weight:
            raise MeatProcessingInvariantError("El peso neto no puede exceder el peso bruto")
        if self.expiration_date is not None and self.expiration_date <= self.production_date:
            raise MeatProcessingInvariantError(
                "La fecha de caducidad debe ser posterior a la de producción")
