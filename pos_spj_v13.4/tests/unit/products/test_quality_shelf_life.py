"""PROD-8 — calidad, vida útil y logística (cadena de frío, temperatura, caducidad)."""

from decimal import Decimal

import pytest

from backend.domain.products.entities.product import Product
from backend.domain.products.entities.product_logistics_profile import (
    ProductLogisticsProfile,
)
from backend.domain.products.entities.product_quality_profile import (
    ProductQualityProfile,
)
from backend.domain.products.entities.product_shelf_life_profile import (
    ProductShelfLifeProfile,
)
from backend.domain.products.enums import ProductType
from backend.domain.products.exceptions import (
    InvalidQualityProfileError,
    InvalidShelfLifeProfileError,
    InvalidTemperatureRangeError,
    ProductsDomainError,
    ShelfLifeRequiredError,
)
from backend.domain.products.policies.shelf_life_policy import require_shelf_life
from backend.domain.products.value_objects.temperature_range import TemperatureRange


# ── temperature range (§18) ──────────────────────────────────────────────────
class TestTemperatureRange:
    def test_valid_and_contains(self):
        tr = TemperatureRange(Decimal("-18"), Decimal("-15"))
        assert tr.contains(Decimal("-16")) and not tr.contains(Decimal("0"))

    def test_float_rejected(self):
        with pytest.raises(InvalidTemperatureRangeError):
            TemperatureRange(-18.0, -15.0)

    def test_min_over_max_rejected(self):
        with pytest.raises(InvalidTemperatureRangeError):
            TemperatureRange(Decimal("5"), Decimal("2"))


# ── shelf life (§19) ─────────────────────────────────────────────────────────
class TestShelfLife:
    def test_valid_profile_gates(self):
        p = ProductShelfLifeProfile(product_id="p1", shelf_life_days=30,
                                    minimum_remaining_for_receipt=20,
                                    minimum_remaining_for_sale=5)
        assert p.accepts_on_receipt(25) and not p.accepts_on_receipt(10)
        assert p.sellable_with_remaining(6) and not p.sellable_with_remaining(3)

    def test_shelf_life_must_be_positive(self):
        with pytest.raises(InvalidShelfLifeProfileError):
            ProductShelfLifeProfile(product_id="p1", shelf_life_days=0)

    def test_receipt_min_cannot_exceed_total(self):
        with pytest.raises(InvalidShelfLifeProfileError):
            ProductShelfLifeProfile(product_id="p1", shelf_life_days=10,
                                    minimum_remaining_for_receipt=20)

    def test_negative_days_rejected(self):
        with pytest.raises(InvalidShelfLifeProfileError):
            ProductShelfLifeProfile(product_id="p1", shelf_life_days=-5)


# ── shelf-life policy (§35) ──────────────────────────────────────────────────
class TestShelfLifePolicy:
    def _perishable(self):
        return Product(code="MEAT-1", name="Pechuga", product_type=ProductType.PRIMARY_CUT,
                       base_unit_id="kg", category_id="c1", species_id="sp1",
                       expiration_controlled=True)

    def test_perishable_without_profile_blocked(self):
        with pytest.raises(ShelfLifeRequiredError):
            require_shelf_life(self._perishable(), has_shelf_life_profile=False)

    def test_perishable_with_profile_ok(self):
        require_shelf_life(self._perishable(), has_shelf_life_profile=True)

    def test_non_perishable_noop(self):
        p = Product(code="ABR", name="Refresco", product_type=ProductType.RESALE_PRODUCT,
                    base_unit_id="pza", category_id="c1")
        require_shelf_life(p, has_shelf_life_profile=False)


# ── quality (§20) ────────────────────────────────────────────────────────────
class TestQuality:
    def test_fat_band_and_membership(self):
        q = ProductQualityProfile(product_id="p1", inspection_required=True,
                                  fat_pct_min=Decimal("10"), fat_pct_max=Decimal("20"))
        assert q.fat_in_range(Decimal("15"))
        assert not q.fat_in_range(Decimal("25"))

    def test_float_percentage_rejected(self):
        with pytest.raises(InvalidQualityProfileError):
            ProductQualityProfile(product_id="p1", fat_pct_min=10.0)

    def test_percentage_out_of_0_100_rejected(self):
        with pytest.raises(InvalidQualityProfileError):
            ProductQualityProfile(product_id="p1", moisture_pct_max=Decimal("150"))

    def test_inverted_band_rejected(self):
        with pytest.raises(InvalidQualityProfileError):
            ProductQualityProfile(product_id="p1", fat_pct_min=Decimal("30"),
                                  fat_pct_max=Decimal("10"))


# ── logistics (§18) ──────────────────────────────────────────────────────────
class TestLogistics:
    def test_frozen_forces_cold_chain(self):
        lg = ProductLogisticsProfile(product_id="p1", frozen=True)
        assert lg.requires_cold_chain

    def test_chilled_forces_cold_chain(self):
        lg = ProductLogisticsProfile(product_id="p1", chilled=True)
        assert lg.requires_cold_chain

    def test_net_over_gross_rejected(self):
        with pytest.raises(ProductsDomainError):
            ProductLogisticsProfile(product_id="p1", gross_weight=Decimal("1"),
                                    net_weight=Decimal("2"))

    def test_float_weight_rejected(self):
        with pytest.raises(ProductsDomainError):
            ProductLogisticsProfile(product_id="p1", gross_weight=1.0)

    def test_temperature_ranges_stored(self):
        lg = ProductLogisticsProfile(
            product_id="p1", frozen=True,
            storage_temperature=TemperatureRange(Decimal("-20"), Decimal("-18")))
        assert lg.storage_temperature.contains(Decimal("-19"))
