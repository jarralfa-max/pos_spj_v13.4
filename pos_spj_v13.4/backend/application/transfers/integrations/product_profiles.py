"""Composition boundary for Product-owned unit, catch-weight and quality rules."""
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from backend.domain.transfers.policies.cold_chain_transfer_policy import ProductTransferProfile


class ProductUnitConversionQueryService(Protocol):
    def is_unit_supported(self, *, product_id: str, unit_id: str) -> bool: ...


class ProductCatchWeightQueryService(Protocol):
    def is_catch_weight(self, product_id: str) -> bool: ...


@dataclass(frozen=True, slots=True)
class ProductQualityTransferRules:
    lot_required: bool
    quality_required: bool
    temperature_required: bool
    minimum_temperature: Decimal | None
    maximum_temperature: Decimal | None
    temperature_warning_margin: Decimal | None


class ProductQualityProfileQueryService(Protocol):
    def get_transfer_rules(self, product_id: str) -> ProductQualityTransferRules: ...


class ProductShelfLifeQueryService(Protocol):
    def requires_expiration_tracking(self, product_id: str) -> bool: ...


class CanonicalProductTransferProfileQueryService:
    def __init__(self, units: ProductUnitConversionQueryService,
                 catch_weight: ProductCatchWeightQueryService,
                 quality: ProductQualityProfileQueryService,
                 shelf_life: ProductShelfLifeQueryService) -> None:
        self._units = units
        self._catch_weight = catch_weight
        self._quality = quality
        self._shelf_life = shelf_life

    def validate_unit(self, *, product_id: str, unit_id: str) -> None:
        if not self._units.is_unit_supported(product_id=product_id, unit_id=unit_id):
            raise ValueError("Product unit is not valid for transfer")

    def get_transfer_profile(self, product_id: str) -> ProductTransferProfile:
        rules = self._quality.get_transfer_rules(product_id)
        return ProductTransferProfile(
            product_id=product_id,
            catch_weight=self._catch_weight.is_catch_weight(product_id),
            lot_required=(rules.lot_required
                          or self._shelf_life.requires_expiration_tracking(product_id)),
            quality_required=rules.quality_required,
            temperature_required=rules.temperature_required,
            minimum_temperature=rules.minimum_temperature,
            maximum_temperature=rules.maximum_temperature,
            temperature_warning_margin=rules.temperature_warning_margin,
        )
