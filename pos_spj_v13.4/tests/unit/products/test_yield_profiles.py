"""PROD-10 — rendimientos multi-especie: outputs, tolerancia, versionado."""

from decimal import Decimal

import pytest

from backend.domain.products.entities.yield_output import YieldOutput
from backend.domain.products.entities.yield_profile import YieldProfile
from backend.domain.products.entities.yield_profile_version import YieldProfileVersion
from backend.domain.products.exceptions import (
    RecipeVersionImmutableError,
    YieldProfileInvalidError,
    YieldToleranceExceededError,
)
from backend.domain.products.recipe_enums import OutputType, RecipeVersionStatus
from backend.domain.products.services.yield_validation_service import (
    YieldValidationService,
)


def _out(pid, pct, otype=OutputType.MAIN_PRODUCT, **kw):
    return YieldOutput(product_id=pid, output_type=otype,
                       expected_yield_pct=Decimal(pct), unit_id="kg", **kw)


# ── output ───────────────────────────────────────────────────────────────────
class TestYieldOutput:
    def test_float_rejected(self):
        with pytest.raises(YieldProfileInvalidError):
            YieldOutput(product_id="p", output_type=OutputType.MAIN_PRODUCT,
                        expected_yield_pct=70.0, unit_id="kg")

    def test_expected_out_of_band_rejected(self):
        with pytest.raises(YieldProfileInvalidError):
            _out("p", "50", minimum_yield_pct=Decimal("60"))

    def test_band_membership(self):
        o = _out("p", "70", minimum_yield_pct=Decimal("65"), maximum_yield_pct=Decimal("75"))
        assert o.yield_in_band(Decimal("72"))
        assert not o.yield_in_band(Decimal("80"))

    def test_inverted_band_rejected(self):
        with pytest.raises(YieldProfileInvalidError):
            _out("p", "70", minimum_yield_pct=Decimal("80"), maximum_yield_pct=Decimal("60"))


# ── profile / version (§22, §23) ─────────────────────────────────────────────
class TestVersion:
    def _draft(self, tol="0"):
        v = YieldProfileVersion(yield_profile_id="yp1", version_number=1,
                                tolerance_pct=Decimal(tol))
        v.add_output(_out("main", "70"))
        v.add_output(_out("bone", "20", OutputType.BY_PRODUCT))
        v.add_output(_out("waste", "10", OutputType.WASTE))
        return v

    def test_total_yield(self):
        assert self._draft().total_expected_yield() == Decimal("100")

    def test_lifecycle_and_immutability(self):
        v = self._draft()
        v.submit(); v.approve(approved_by_user_id="mgr"); v.activate()
        assert v.status is RecipeVersionStatus.ACTIVE
        with pytest.raises(RecipeVersionImmutableError):
            v.add_output(_out("x", "1"))

    def test_cannot_submit_without_outputs(self):
        v = YieldProfileVersion(yield_profile_id="yp1", version_number=1)
        with pytest.raises(YieldProfileInvalidError):
            v.submit()

    def test_tolerance_bounds(self):
        with pytest.raises(YieldProfileInvalidError):
            YieldProfileVersion(yield_profile_id="yp1", version_number=1,
                                tolerance_pct=Decimal("150"))


# ── validation service (§23 sin 100% hardcodeado) ───────────────────────────
class TestValidation:
    def _version(self, outs, tol="0"):
        v = YieldProfileVersion(yield_profile_id="yp1", version_number=1,
                                tolerance_pct=Decimal(tol))
        for pid, pct, ot in outs:
            v.add_output(_out(pid, pct, ot))
        return v

    def test_exact_100_ok(self):
        v = self._version([("m", "70", OutputType.MAIN_PRODUCT),
                           ("b", "30", OutputType.BY_PRODUCT)])
        YieldValidationService().validate(v)

    def test_within_tolerance_band(self):
        # suma 98, tolerancia 5 → válido (no exige 100 exacto)
        v = self._version([("m", "70", OutputType.MAIN_PRODUCT),
                           ("b", "28", OutputType.BY_PRODUCT)], tol="5")
        assert YieldValidationService().is_within_tolerance(v)

    def test_outside_tolerance_rejected(self):
        v = self._version([("m", "70", OutputType.MAIN_PRODUCT),
                           ("b", "20", OutputType.BY_PRODUCT)], tol="5")  # suma 90
        with pytest.raises(YieldToleranceExceededError):
            YieldValidationService().validate(v)

    def test_duplicate_output_product_rejected(self):
        v = self._version([("m", "50", OutputType.MAIN_PRODUCT),
                           ("m", "50", OutputType.CO_PRODUCT)])
        with pytest.raises(YieldProfileInvalidError):
            YieldValidationService().validate(v)

    def test_empty_rejected(self):
        v = YieldProfileVersion(yield_profile_id="yp1", version_number=1)
        with pytest.raises(YieldProfileInvalidError):
            YieldValidationService().validate(v)


# ── profile entity ───────────────────────────────────────────────────────────
class TestProfile:
    def test_profile_requires_input(self):
        with pytest.raises(YieldProfileInvalidError):
            YieldProfile(input_product_id="", name="Canal bovina")

    def test_profile_multi_species(self):
        # perfiles distintos por especie, sin hardcode
        bov = YieldProfile(input_product_id="canal-bov", name="Canal bovina", species_id="bov")
        por = YieldProfile(input_product_id="canal-por", name="Canal porcina", species_id="por")
        assert bov.species_id != por.species_id
