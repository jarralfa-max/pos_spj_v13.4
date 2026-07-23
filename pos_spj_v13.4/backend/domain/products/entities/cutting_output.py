"""CuttingOutput — one output of a cutting-scheme version (§24).

A disassembly output: a cut (with its classification, level and bone status)
produced from the input, measured either by piece or by weight (never both from
one another). Waste/loss are outputs too. Decimal-only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import Enum

from backend.domain.products.exceptions import CuttingSchemeInvalidError
from backend.domain.products.meat_enums import BoneStatus, CutLevel
from backend.domain.products.recipe_enums import OutputType
from backend.shared.ids import new_uuid


class MeasureKind(str, Enum):
    BY_PIECE = "BY_PIECE"
    BY_WEIGHT = "BY_WEIGHT"


def _dec(value, label: str) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise CuttingSchemeInvalidError(f"{label} no puede ser float")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise CuttingSchemeInvalidError(f"{label} inválido: {value!r}") from exc


@dataclass
class CuttingOutput:
    product_id: str
    measure_kind: MeasureKind
    quantity: Decimal
    unit_id: str
    id: str = field(default_factory=new_uuid)
    version_id: str | None = None
    output_type: OutputType = OutputType.MAIN_PRODUCT
    cut_classification_id: str | None = None
    cut_level: CutLevel | None = None
    bone_status: BoneStatus = BoneStatus.NOT_APPLICABLE
    sequence: int = 0

    def __post_init__(self) -> None:
        if not self.product_id:
            raise CuttingSchemeInvalidError("El output de despiece requiere producto")
        if not self.unit_id:
            raise CuttingSchemeInvalidError("El output de despiece requiere unidad")
        if not isinstance(self.measure_kind, MeasureKind):
            try:
                self.measure_kind = MeasureKind(str(self.measure_kind))
            except ValueError as exc:
                raise CuttingSchemeInvalidError(
                    f"Tipo de medida inválido: {self.measure_kind!r}") from exc
        if not isinstance(self.output_type, OutputType):
            self.output_type = OutputType(str(self.output_type))
        if self.cut_level is not None and not isinstance(self.cut_level, CutLevel):
            self.cut_level = CutLevel(str(self.cut_level))
        if not isinstance(self.bone_status, BoneStatus):
            self.bone_status = BoneStatus(str(self.bone_status))
        self.quantity = _dec(self.quantity, "quantity")
        if self.quantity < 0:
            raise CuttingSchemeInvalidError("La cantidad del output no puede ser negativa")
