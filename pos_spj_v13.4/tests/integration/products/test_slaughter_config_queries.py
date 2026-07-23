"""PROD-12 — QueryServices de contrato para sacrificio (solo lectura, sin ejecución)."""

import sqlite3
from decimal import Decimal

import pytest

from backend.application.products.queries.slaughter_config_query_service import (
    ActiveCuttingSchemeQueryService,
    ActiveYieldProfileQueryService,
    AnimalInputConfigurationQueryService,
    CarcassProductConfigurationQueryService,
    SlaughterOutputDefinitionQueryService,
)
from backend.domain.products.entities.cutting_output import CuttingOutput, MeasureKind
from backend.domain.products.entities.cutting_scheme import CuttingScheme
from backend.domain.products.entities.cutting_scheme_version import (
    CuttingSchemeVersion,
)
from backend.domain.products.entities.product_logistics_profile import (
    ProductLogisticsProfile,
)
from backend.domain.products.entities.product_quality_profile import (
    ProductQualityProfile,
)
from backend.domain.products.entities.yield_output import YieldOutput
from backend.domain.products.entities.yield_profile import YieldProfile
from backend.domain.products.entities.yield_profile_version import YieldProfileVersion
from backend.domain.products.recipe_enums import OutputType
from backend.infrastructure.db.repositories.products.cutting_scheme_repository import (
    CuttingSchemeRepository,
)
from backend.infrastructure.db.repositories.products.profile_repository import (
    ProfileRepository,
)
from backend.infrastructure.db.repositories.products.yield_repository import (
    YieldRepository,
)
from backend.infrastructure.db.schema.products_schema import create_products_schema


def _product(c, pid, ptype, **flags):
    cols = dict(sellable=0, catch_weight_enabled=0, lot_controlled=0,
                traceability_required=0, quality_controlled=0, species_id="bov")
    cols.update(flags)
    c.execute(
        """INSERT INTO products (id,code,name,name_normalized,product_type,
           lifecycle_status,base_unit_id,species_id,catch_weight_enabled,lot_controlled,
           traceability_required,quality_controlled)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (pid, pid.upper(), pid, pid, ptype, "ACTIVE", "kg", cols["species_id"],
         cols["catch_weight_enabled"], cols["lot_controlled"],
         cols["traceability_required"], cols["quality_controlled"]))


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_products_schema(c)
    c.execute("INSERT INTO species (id,code,name) VALUES ('bov','BOVINE','Bovino')")
    _product(c, "novillo", "LIVE_ANIMAL", catch_weight_enabled=1, traceability_required=1,
             lot_controlled=1, quality_controlled=1)
    _product(c, "canal", "CARCASS", quality_controlled=1)
    for cut in ("lomo", "hueso", "costilla"):
        _product(c, cut, "PRIMARY_CUT")

    # carcass profiles
    prof = ProfileRepository(c)
    prof.save_shelf_life(__import__(
        "backend.domain.products.entities.product_shelf_life_profile", fromlist=["x"]
    ).ProductShelfLifeProfile(product_id="canal", shelf_life_days=21))
    prof.save_logistics(ProductLogisticsProfile(product_id="canal", chilled=True))
    prof.save_quality(ProductQualityProfile(product_id="canal", inspection_required=True,
                                            quarantine_required=True))

    # yield profile for novillo → cuts
    yr = YieldRepository(c)
    yp = YieldProfile(input_product_id="novillo", name="Rendimiento novillo", species_id="bov")
    yr.save_profile(yp)
    yv = YieldProfileVersion(yield_profile_id=yp.id, version_number=1,
                             tolerance_pct=Decimal("2"))
    yv.add_output(YieldOutput(product_id="lomo", output_type=OutputType.MAIN_PRODUCT,
                              expected_yield_pct=Decimal("60"), unit_id="kg"))
    yv.add_output(YieldOutput(product_id="hueso", output_type=OutputType.BY_PRODUCT,
                              expected_yield_pct=Decimal("40"), unit_id="kg"))
    yv.submit(); yv.approve(approved_by_user_id="mgr"); yv.activate()
    yr.save_version(yv)

    # cutting scheme for canal → cuts
    cr = CuttingSchemeRepository(c)
    cs = CuttingScheme(input_product_id="canal", species_id="bov", name="Despiece canal")
    cr.save_scheme(cs)
    cv = CuttingSchemeVersion(cutting_scheme_id=cs.id, version_number=1)
    cv.add_output(CuttingOutput(product_id="lomo", measure_kind=MeasureKind.BY_WEIGHT,
                                quantity=Decimal("12"), unit_id="kg"))
    cv.add_output(CuttingOutput(product_id="costilla", measure_kind=MeasureKind.BY_PIECE,
                                quantity=Decimal("8"), unit_id="pza"))
    cv.submit(); cv.approve(approved_by_user_id="mgr"); cv.activate()
    cr.save_version(cv)
    c.commit()
    yield c
    c.close()


def test_animal_input_config(conn):
    dto = AnimalInputConfigurationQueryService(conn).get("novillo")
    assert dto is not None
    assert dto.species_id == "bov" and dto.catch_weight_enabled and dto.traceability_required

def test_animal_input_none_for_non_animal(conn):
    assert AnimalInputConfigurationQueryService(conn).get("canal") is None


def test_carcass_config(conn):
    dto = CarcassProductConfigurationQueryService(conn).get("canal")
    assert dto is not None
    assert dto.shelf_life_days == 21 and dto.requires_cold_chain
    assert dto.inspection_required and dto.quarantine_required

def test_carcass_none_for_animal(conn):
    assert CarcassProductConfigurationQueryService(conn).get("novillo") is None


def test_active_yield_profile(conn):
    dto = ActiveYieldProfileQueryService(conn).get_for_input("novillo")
    assert dto is not None and dto.tolerance_pct == Decimal("2")
    assert {o.product_id for o in dto.outputs} == {"lomo", "hueso"}

def test_active_cutting_scheme(conn):
    dto = ActiveCuttingSchemeQueryService(conn).get_for_input("canal")
    assert dto is not None and dto.species_id == "bov"
    assert {o.product_id for o in dto.outputs} == {"lomo", "costilla"}


def test_slaughter_output_definition_union(conn):
    dto = SlaughterOutputDefinitionQueryService(conn).get_for_input("canal")
    # canal tiene despiece (lomo, costilla); sin perfil de rendimiento propio
    assert set(dto.cutting_output_product_ids) == {"lomo", "costilla"}
    assert set(dto.all_output_product_ids) == {"lomo", "costilla"}

def test_slaughter_definition_for_animal_uses_yield(conn):
    dto = SlaughterOutputDefinitionQueryService(conn).get_for_input("novillo")
    assert set(dto.yield_output_product_ids) == {"lomo", "hueso"}
    assert SlaughterOutputDefinitionQueryService(conn).is_meat_input("novillo")


# ── contrato solo-lectura (§25: Productos no registra ejecución) ─────────────
def test_query_services_have_no_execution_methods(conn):
    forbidden = ("record", "save", "register", "post", "execute", "create",
                 "update", "delete", "slaughter", "kill")
    services = [
        AnimalInputConfigurationQueryService(conn),
        CarcassProductConfigurationQueryService(conn),
        ActiveYieldProfileQueryService(conn),
        ActiveCuttingSchemeQueryService(conn),
        SlaughterOutputDefinitionQueryService(conn),
    ]
    for svc in services:
        methods = [m for m in dir(svc) if not m.startswith("_")]
        for m in methods:
            assert not any(m.lower().startswith(f) for f in forbidden), \
                f"{type(svc).__name__}.{m} parece escritura/ejecución (§25)"
