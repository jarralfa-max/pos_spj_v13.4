"""Commands del catálogo de unidades, conversiones y peso variable (PROD-5)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CreateUnitCommand:
    operation_id: str
    code: str
    name: str
    dimension: str
    user_id: str | None = None

    def validate(self) -> None:
        missing = [f for f in ("operation_id", "code", "name", "dimension")
                   if not getattr(self, f)]
        if missing:
            raise ValueError(f"Faltan campos requeridos: {', '.join(missing)}")


@dataclass(frozen=True)
class SetUnitActiveCommand:
    operation_id: str
    unit_id: str
    active: bool
    user_id: str | None = None

    def validate(self) -> None:
        missing = [f for f in ("operation_id", "unit_id") if not getattr(self, f)]
        if missing:
            raise ValueError(f"Faltan campos requeridos: {', '.join(missing)}")


@dataclass(frozen=True)
class CreateUnitConversionCommand:
    operation_id: str
    from_unit_id: str
    to_unit_id: str
    factor: str
    user_id: str | None = None
    product_id: str | None = None          # None = conversión global
    rounding_scale: int = 6
    effective_from: str | None = None
    effective_to: str | None = None

    def validate(self) -> None:
        missing = [f for f in ("operation_id", "from_unit_id", "to_unit_id", "factor")
                   if not getattr(self, f)]
        if missing:
            raise ValueError(f"Faltan campos requeridos: {', '.join(missing)}")


@dataclass(frozen=True)
class SetCatchWeightConfigCommand:
    operation_id: str
    product_id: str
    enabled: bool
    user_id: str | None = None
    nominal_unit_id: str | None = None
    weight_unit_id: str | None = None
    minimum_weight: str | None = None
    maximum_weight: str | None = None
    average_weight: str | None = None
    tolerance_pct: str = "0"
    price_basis: str = "PER_KILOGRAM"
    label_required: bool = True
    scale_barcode_enabled: bool = False

    def validate(self) -> None:
        missing = [f for f in ("operation_id", "product_id") if not getattr(self, f)]
        if missing:
            raise ValueError(f"Faltan campos requeridos: {', '.join(missing)}")
