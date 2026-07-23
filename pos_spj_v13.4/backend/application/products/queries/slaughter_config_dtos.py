"""Slaughter-preparation configuration DTOs (§25).

Read-only, immutable payloads the *future* slaughter/production module will consult
to know the technical model: the animal input, the carcass product, the active
yield profile and cutting scheme, and the full set of expected outputs. Products
defines this model; it NEVER records real execution (live/carcass weight,
mortality, condemnation, real yield, slaughter lot) — those belong to the
operational module. Decimal-safe.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from backend.domain.products.recipe_enums import OutputType


@dataclass(frozen=True)
class AnimalInputConfigurationDTO:
    product_id: str
    product_type: str
    species_id: str | None
    base_unit_id: str
    catch_weight_enabled: bool
    lot_controlled: bool
    traceability_required: bool
    quality_controlled: bool


@dataclass(frozen=True)
class CarcassProductConfigurationDTO:
    product_id: str
    product_type: str
    species_id: str | None
    base_unit_id: str
    shelf_life_days: int | None
    requires_cold_chain: bool
    inspection_required: bool
    quarantine_required: bool


@dataclass(frozen=True)
class YieldOutputDTO:
    product_id: str
    output_type: OutputType
    expected_yield_pct: Decimal
    minimum_yield_pct: Decimal | None
    maximum_yield_pct: Decimal | None
    unit_id: str
    cost_allocation_weight: Decimal


@dataclass(frozen=True)
class ActiveYieldProfileDTO:
    yield_profile_id: str
    version_id: str
    version_number: int
    species_id: str | None
    input_product_id: str
    tolerance_pct: Decimal
    outputs: tuple[YieldOutputDTO, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CuttingOutputDTO:
    product_id: str
    output_type: OutputType
    measure_kind: str
    quantity: Decimal
    unit_id: str
    bone_status: str
    cut_level: str | None


@dataclass(frozen=True)
class ActiveCuttingSchemeDTO:
    cutting_scheme_id: str
    version_id: str
    version_number: int
    species_id: str
    input_product_id: str
    cut_level: str
    outputs: tuple[CuttingOutputDTO, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SlaughterOutputDefinitionDTO:
    """The full set of outputs the future slaughter expects for an input product."""

    input_product_id: str
    species_id: str | None
    yield_output_product_ids: tuple[str, ...] = field(default_factory=tuple)
    cutting_output_product_ids: tuple[str, ...] = field(default_factory=tuple)

    @property
    def all_output_product_ids(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(
            self.yield_output_product_ids + self.cutting_output_product_ids))
