"""PROD-3 — clasificación cárnica multi-especie: Species/Region/Cut + policy."""

import pytest

from backend.domain.products.entities.anatomical_region import AnatomicalRegion
from backend.domain.products.entities.cut_classification import CutClassification
from backend.domain.products.entities.species import Species
from backend.domain.products.enums import ProductType
from backend.domain.products.exceptions import (
    ProductsDomainError,
    SpeciesRequiredError,
)
from backend.domain.products.meat_enums import (
    BoneStatus,
    CutLevel,
    MeatCategory,
    MeatSpeciesCode,
)
from backend.domain.products.policies.meat_product_classification_policy import (
    requires_classification,
    validate_product_classification,
)


# ── no chicken-only (§11) ────────────────────────────────────────────────────
class TestMultiSpecies:
    def test_species_codes_cover_multiple_animals(self):
        codes = {c.value for c in MeatSpeciesCode}
        for expected in ("POULTRY", "BOVINE", "PORCINE", "OVINE", "FISH"):
            assert expected in codes
        assert len(codes) >= 8  # nunca solo pollo

    def test_meat_category_covers_carcass_and_offal(self):
        vals = {c.value for c in MeatCategory}
        assert {"CARCASS", "HALF_CARCASS", "QUARTER", "OFFAL", "WASTE"} <= vals


# ── entidades de catálogo ────────────────────────────────────────────────────
class TestSpecies:
    def test_species_normalizes_code(self):
        s = Species(code="bovine", name="Bovino")
        assert s.code == "BOVINE" and len(s.id) >= 32

    def test_species_requires_code_and_name(self):
        with pytest.raises(ProductsDomainError):
            Species(code="", name="x")
        with pytest.raises(ProductsDomainError):
            Species(code="BOVINE", name="")


class TestAnatomicalRegion:
    def test_region_requires_species(self):
        with pytest.raises(ProductsDomainError):
            AnatomicalRegion(species_id="", code="LOIN", name="Lomo")

    def test_region_ok(self):
        r = AnatomicalRegion(species_id="sp1", code="loin", name="Lomo")
        assert r.code == "LOIN" and r.species_id == "sp1"


class TestCutClassification:
    def test_cut_requires_species_and_region(self):
        with pytest.raises(ProductsDomainError):
            CutClassification(species_id="", anatomical_region_id="r1",
                              code="C", name="Corte", cut_level=CutLevel.PRIMARY)
        with pytest.raises(ProductsDomainError):
            CutClassification(species_id="s1", anatomical_region_id="",
                              code="C", name="Corte", cut_level=CutLevel.PRIMARY)

    def test_cut_hierarchy_valid(self):
        canal = CutClassification(species_id="s1", anatomical_region_id="r1",
                                  code="CANAL", name="Canal", cut_level=CutLevel.CARCASS)
        primario = CutClassification(species_id="s1", anatomical_region_id="r1",
                                     code="PRIM", name="Primario",
                                     cut_level=CutLevel.PRIMARY, parent_cut_id=canal.id)
        primario.validate_under_parent(canal)  # no raise

    def test_cut_child_must_be_below_parent(self):
        primario = CutClassification(species_id="s1", anatomical_region_id="r1",
                                     code="PRIM", name="Primario", cut_level=CutLevel.PRIMARY)
        canal = CutClassification(species_id="s1", anatomical_region_id="r1",
                                  code="CANAL", name="Canal", cut_level=CutLevel.CARCASS)
        # canal (nivel 0) no puede colgar de primario (nivel 1)
        with pytest.raises(ProductsDomainError):
            canal.validate_under_parent(primario)

    def test_cut_child_must_be_same_species(self):
        parent = CutClassification(species_id="s1", anatomical_region_id="r1",
                                   code="CANAL", name="Canal", cut_level=CutLevel.CARCASS)
        child = CutClassification(species_id="s2", anatomical_region_id="r2",
                                  code="PRIM", name="Primario", cut_level=CutLevel.PRIMARY)
        with pytest.raises(ProductsDomainError):
            child.validate_under_parent(parent)

    def test_cut_cannot_be_own_parent(self):
        c = CutClassification(species_id="s1", anatomical_region_id="r1",
                              code="X", name="X", cut_level=CutLevel.PRIMARY)
        with pytest.raises(ProductsDomainError):
            c.validate_under_parent(c)

    def test_cut_bone_status_default(self):
        c = CutClassification(species_id="s1", anatomical_region_id="r1",
                              code="X", name="X", cut_level=CutLevel.SECONDARY,
                              bone_status=BoneStatus.BONELESS)
        assert c.bone_status is BoneStatus.BONELESS


# ── classification policy ────────────────────────────────────────────────────
class TestClassificationPolicy:
    def test_requires_classification_for_meat_types(self):
        assert requires_classification(ProductType.PRIMARY_CUT)
        assert not requires_classification(ProductType.RESALE_PRODUCT)

    def test_meat_without_species_rejected(self):
        with pytest.raises(SpeciesRequiredError):
            validate_product_classification(
                product_type=ProductType.OFFAL, species=None, cut=None)

    def test_non_meat_skips_classification(self):
        validate_product_classification(
            product_type=ProductType.RESALE_PRODUCT, species=None, cut=None)

    def test_cut_species_must_match_product_species(self):
        sp = Species(code="BOVINE", name="Bovino")
        other_cut = CutClassification(species_id="other", anatomical_region_id="r1",
                                      code="X", name="X", cut_level=CutLevel.PRIMARY)
        with pytest.raises(ProductsDomainError):
            validate_product_classification(
                product_type=ProductType.PRIMARY_CUT, species=sp, cut=other_cut)

    def test_valid_meat_classification(self):
        sp = Species(code="BOVINE", name="Bovino")
        region = AnatomicalRegion(species_id=sp.id, code="LOIN", name="Lomo")
        cut = CutClassification(species_id=sp.id, anatomical_region_id=region.id,
                                code="RIBEYE", name="Rib Eye", cut_level=CutLevel.SECONDARY)
        validate_product_classification(
            product_type=ProductType.SECONDARY_CUT, species=sp, cut=cut, region=region)
