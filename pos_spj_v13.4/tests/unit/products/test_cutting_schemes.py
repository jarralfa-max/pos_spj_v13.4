"""PROD-11 — esquemas de despiece multi-especie: niveles, hueso/pieza/peso, ciclo."""

from decimal import Decimal

import pytest

from backend.domain.products.entities.cutting_output import CuttingOutput, MeasureKind
from backend.domain.products.entities.cutting_scheme import CuttingScheme
from backend.domain.products.entities.cutting_scheme_version import (
    CuttingSchemeVersion,
)
from backend.domain.products.exceptions import (
    CuttingSchemeCycleDetectedError,
    CuttingSchemeInvalidError,
    RecipeVersionImmutableError,
)
from backend.domain.products.meat_enums import BoneStatus, CutLevel
from backend.domain.products.recipe_enums import OutputType
from backend.domain.products.services.cutting_scheme_service import CuttingSchemeService


def _out(pid, kind=MeasureKind.BY_WEIGHT, qty="1", **kw):
    return CuttingOutput(product_id=pid, measure_kind=kind, quantity=Decimal(qty),
                         unit_id="kg", **kw)


# ── output ───────────────────────────────────────────────────────────────────
class TestCuttingOutput:
    def test_float_rejected(self):
        with pytest.raises(CuttingSchemeInvalidError):
            CuttingOutput(product_id="p", measure_kind=MeasureKind.BY_WEIGHT,
                          quantity=1.5, unit_id="kg")

    def test_by_piece_and_bone_status(self):
        o = _out("p", MeasureKind.BY_PIECE, "12", bone_status=BoneStatus.BONELESS,
                 cut_level=CutLevel.SECONDARY)
        assert o.measure_kind is MeasureKind.BY_PIECE
        assert o.bone_status is BoneStatus.BONELESS and o.cut_level is CutLevel.SECONDARY

    def test_measure_kind_coercion(self):
        assert _out("p", "BY_WEIGHT").measure_kind is MeasureKind.BY_WEIGHT

    def test_negative_qty_rejected(self):
        with pytest.raises(CuttingSchemeInvalidError):
            _out("p", qty="-1")


# ── scheme (§24 multi-especie) ───────────────────────────────────────────────
class TestScheme:
    def test_scheme_requires_species(self):
        with pytest.raises(CuttingSchemeInvalidError):
            CuttingScheme(input_product_id="canal", species_id="", name="X")

    def test_multi_species_schemes(self):
        bov = CuttingScheme(input_product_id="canal-bov", species_id="bov",
                            name="Despiece bovino", cut_level=CutLevel.PRIMARY)
        por = CuttingScheme(input_product_id="canal-por", species_id="por",
                            name="Despiece porcino")
        assert bov.species_id != por.species_id


# ── version (§22) ────────────────────────────────────────────────────────────
class TestVersion:
    def _draft(self):
        v = CuttingSchemeVersion(cutting_scheme_id="cs1", version_number=1)
        v.add_output(_out("lomo")); v.add_output(_out("costilla", MeasureKind.BY_PIECE, "8"))
        return v

    def test_lifecycle_and_immutability(self):
        v = self._draft()
        v.submit(); v.approve(approved_by_user_id="mgr"); v.activate()
        assert v.status.value == "ACTIVE"
        with pytest.raises(RecipeVersionImmutableError):
            v.add_output(_out("x"))

    def test_cannot_submit_empty(self):
        v = CuttingSchemeVersion(cutting_scheme_id="cs1", version_number=1)
        with pytest.raises(CuttingSchemeInvalidError):
            v.submit()


# ── service ──────────────────────────────────────────────────────────────────
class TestService:
    def _scheme(self, input_pid="canal"):
        return CuttingScheme(input_product_id=input_pid, species_id="bov", name="X")

    def test_valid_scheme(self):
        v = CuttingSchemeVersion(cutting_scheme_id="cs1", version_number=1)
        v.add_output(_out("lomo")); v.add_output(_out("hueso", output_type=OutputType.BY_PRODUCT))
        CuttingSchemeService().validate(self._scheme(), v)

    def test_self_containing_rejected(self):
        v = CuttingSchemeVersion(cutting_scheme_id="cs1", version_number=1)
        v.add_output(_out("canal"))   # el input aparece como output
        with pytest.raises(CuttingSchemeCycleDetectedError):
            CuttingSchemeService().validate(self._scheme("canal"), v)

    def test_duplicate_output_rejected(self):
        v = CuttingSchemeVersion(cutting_scheme_id="cs1", version_number=1)
        v.add_output(_out("lomo")); v.add_output(_out("lomo"))
        with pytest.raises(CuttingSchemeInvalidError):
            CuttingSchemeService().validate(self._scheme(), v)

    def test_empty_rejected(self):
        v = CuttingSchemeVersion(cutting_scheme_id="cs1", version_number=1)
        with pytest.raises(CuttingSchemeInvalidError):
            CuttingSchemeService().validate(self._scheme(), v)
