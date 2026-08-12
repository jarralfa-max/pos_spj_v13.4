"""ProductionPlanLine entity (§11). The plan does not move inventory — a line
only tracks how much demand has been converted into real ProcessingOrder(s)
via `record_conversion()`; PROC-6+ builds the use case that actually creates
the order and calls this."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from backend.domain.meat_processing.entities._validation import (
    decimal_value,
    optional_uuid,
    required_uuid,
)
from backend.domain.meat_processing.enums import PlanSourceType
from backend.domain.meat_processing.exceptions import MeatProcessingInvariantError


@dataclass
class ProductionPlanLine:
    id: str
    product_id: str
    source_type: PlanSourceType
    planned_quantity: Decimal = Decimal("0")
    planned_weight: Decimal = Decimal("0")
    source_reference_id: str | None = None
    required_date: datetime | None = None
    priority: int = 0
    converted_quantity: Decimal = Decimal("0")
    converted_weight: Decimal = Decimal("0")
    converted_processing_order_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        self.id = required_uuid(self.id, "id")
        self.product_id = required_uuid(self.product_id, "product_id")
        self.source_reference_id = optional_uuid(self.source_reference_id, "source_reference_id")
        self.converted_processing_order_ids = tuple(
            required_uuid(order_id, "processing_order_id")
            for order_id in self.converted_processing_order_ids)
        for name in ("planned_quantity", "planned_weight", "converted_quantity",
                     "converted_weight"):
            setattr(self, name, decimal_value(getattr(self, name), name))
        if not isinstance(self.source_type, PlanSourceType):
            raise MeatProcessingInvariantError("Fuente de plan canónica requerida")
        if self.planned_quantity < 0 or self.planned_weight < 0:
            raise MeatProcessingInvariantError("Cantidad y peso planeados no pueden ser negativos")
        if self.planned_quantity == 0 and self.planned_weight == 0:
            raise MeatProcessingInvariantError("La línea requiere cantidad o peso planeado positivo")
        if self.converted_quantity < 0 or self.converted_weight < 0:
            raise MeatProcessingInvariantError("Cantidad y peso convertidos no pueden ser negativos")
        if self.converted_quantity > self.planned_quantity:
            raise MeatProcessingInvariantError("La cantidad convertida no puede exceder la planeada")
        if self.converted_weight > self.planned_weight:
            raise MeatProcessingInvariantError("El peso convertido no puede exceder el planeado")

    def record_conversion(self, *, processing_order_id: str,
                           converted_quantity: Decimal = Decimal("0"),
                           converted_weight: Decimal = Decimal("0")) -> None:
        order_id = required_uuid(processing_order_id, "processing_order_id")
        quantity = decimal_value(converted_quantity, "converted_quantity")
        weight = decimal_value(converted_weight, "converted_weight")
        if quantity < 0 or weight < 0:
            raise MeatProcessingInvariantError("La conversión no puede ser negativa")
        if quantity == 0 and weight == 0:
            raise MeatProcessingInvariantError("La conversión requiere cantidad o peso positivo")
        if self.converted_quantity + quantity > self.planned_quantity:
            raise MeatProcessingInvariantError(
                "La conversión excede la cantidad planeada restante")
        if self.converted_weight + weight > self.planned_weight:
            raise MeatProcessingInvariantError("La conversión excede el peso planeado restante")
        self.converted_quantity += quantity
        self.converted_weight += weight
        if order_id not in self.converted_processing_order_ids:
            self.converted_processing_order_ids += (order_id,)

    @property
    def remaining_quantity(self) -> Decimal:
        return self.planned_quantity - self.converted_quantity

    @property
    def remaining_weight(self) -> Decimal:
        return self.planned_weight - self.converted_weight

    @property
    def is_fully_converted(self) -> bool:
        quantity_done = self.planned_quantity == 0 or self.converted_quantity >= self.planned_quantity
        weight_done = self.planned_weight == 0 or self.converted_weight >= self.planned_weight
        return quantity_done and weight_done

    @property
    def is_partially_converted(self) -> bool:
        return not self.is_fully_converted and (
            self.converted_quantity > 0 or self.converted_weight > 0)
