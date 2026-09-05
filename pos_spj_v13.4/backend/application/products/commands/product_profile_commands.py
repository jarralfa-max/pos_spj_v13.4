"""Commands de perfiles de calidad, vida útil y logística (PROD-8)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SetShelfLifeProfileCommand:
    operation_id: str
    product_id: str
    shelf_life_days: int
    user_id: str | None = None
    minimum_remaining_for_receipt: int = 0
    minimum_remaining_for_sale: int = 0
    storage_condition: str = "AMBIENT"
    opened_shelf_life_days: int = 0
    frozen_shelf_life_days: int = 0
    thawed_shelf_life_days: int = 0
    effective_from: str | None = None
    effective_to: str | None = None

    def validate(self) -> None:
        missing = [f for f in ("operation_id", "product_id")
                   if not getattr(self, f)]
        if missing:
            raise ValueError(f"Faltan campos requeridos: {', '.join(missing)}")
        if self.shelf_life_days is None:
            raise ValueError("shelf_life_days es requerido")


@dataclass(frozen=True)
class SetQualityProfileCommand:
    operation_id: str
    product_id: str
    user_id: str | None = None
    inspection_required: bool = False
    temperature_required: bool = False
    weight_check_required: bool = False
    organoleptic_check_required: bool = False
    microbiological_test_required: bool = False
    fat_pct_min: str | None = None
    fat_pct_max: str | None = None
    moisture_pct_min: str | None = None
    moisture_pct_max: str | None = None
    color_requirement: str | None = None
    odor_requirement: str | None = None
    packaging_requirement: str | None = None
    documentation_requirement: str | None = None
    quarantine_required: bool = False

    def validate(self) -> None:
        missing = [f for f in ("operation_id", "product_id") if not getattr(self, f)]
        if missing:
            raise ValueError(f"Faltan campos requeridos: {', '.join(missing)}")


@dataclass(frozen=True)
class SetLogisticsProfileCommand:
    operation_id: str
    product_id: str
    user_id: str | None = None
    gross_weight: str | None = None
    net_weight: str | None = None
    weight_unit: str = "KG"
    dimensions: str | None = None
    storage_temp_min: str | None = None
    storage_temp_max: str | None = None
    storage_temp_unit: str = "C"
    transport_temp_min: str | None = None
    transport_temp_max: str | None = None
    transport_temp_unit: str = "C"
    fragile: bool = False
    perishable: bool = False
    frozen: bool = False
    chilled: bool = False
    stackable: bool = True
    shelf_life_days: int = 0
    open_package_shelf_life_days: int = 0

    def validate(self) -> None:
        missing = [f for f in ("operation_id", "product_id") if not getattr(self, f)]
        if missing:
            raise ValueError(f"Faltan campos requeridos: {', '.join(missing)}")
