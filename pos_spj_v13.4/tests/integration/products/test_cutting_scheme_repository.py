"""PROD-11 — persistencia de esquemas de despiece versionados."""

import sqlite3
from decimal import Decimal

import pytest

from backend.domain.products.entities.cutting_output import CuttingOutput, MeasureKind
from backend.domain.products.entities.cutting_scheme import CuttingScheme
from backend.domain.products.entities.cutting_scheme_version import (
    CuttingSchemeVersion,
)
from backend.domain.products.meat_enums import BoneStatus, CutLevel
from backend.domain.products.recipe_enums import OutputType
from backend.infrastructure.db.repositories.products.cutting_scheme_repository import (
    CuttingSchemeRepository,
)
from backend.infrastructure.db.schema.products_schema import create_products_schema


@pytest.fixture
def repo():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_products_schema(c)
    c.execute("INSERT INTO species (id,code,name) VALUES ('bov','BOVINE','Bovino')")
    for pid in ("canal", "lomo", "costilla"):
        c.execute("INSERT INTO products (id,code,name,name_normalized,product_type,"
                  "lifecycle_status,base_unit_id) VALUES (?,?,?,?,?,?,?)",
                  (pid, pid.upper(), pid, pid, "PRIMARY_CUT", "ACTIVE", "kg"))
    c.commit()
    yield CuttingSchemeRepository(c)
    c.close()


def _active(repo):
    s = CuttingScheme(input_product_id="canal", species_id="bov",
                      name="Despiece bovino", cut_level=CutLevel.PRIMARY)
    repo.save_scheme(s)
    v = CuttingSchemeVersion(cutting_scheme_id=s.id, version_number=1)
    v.add_output(CuttingOutput(product_id="lomo", measure_kind=MeasureKind.BY_WEIGHT,
                               quantity=Decimal("12.5"), unit_id="kg",
                               bone_status=BoneStatus.BONELESS, cut_level=CutLevel.SECONDARY))
    v.add_output(CuttingOutput(product_id="costilla", measure_kind=MeasureKind.BY_PIECE,
                               quantity=Decimal("8"), unit_id="pza",
                               output_type=OutputType.CO_PRODUCT))
    v.submit(); v.approve(approved_by_user_id="mgr"); v.activate()
    repo.save_version(v)
    return s, v


def test_version_round_trip(repo):
    _s, v = _active(repo)
    got = repo.get_version(v.id)
    assert got.status.value == "ACTIVE" and len(got.outputs) == 2
    lomo = next(o for o in got.outputs if o.product_id == "lomo")
    assert lomo.quantity == Decimal("12.5") and lomo.bone_status is BoneStatus.BONELESS
    cost = next(o for o in got.outputs if o.product_id == "costilla")
    assert cost.measure_kind is MeasureKind.BY_PIECE


def test_active_version_for_input(repo):
    _active(repo)
    got = repo.active_version_for_input("canal")
    assert got is not None and set(got.output_product_ids()) == {"lomo", "costilla"}


def test_scheme_round_trip(repo):
    s, _v = _active(repo)
    got = repo.get_scheme(s.id)
    assert got.species_id == "bov" and got.cut_level is CutLevel.PRIMARY
