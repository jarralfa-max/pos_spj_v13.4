"""PROD-10 — persistencia de perfiles de rendimiento versionados."""

import sqlite3
from decimal import Decimal

import pytest

from backend.domain.products.entities.yield_output import YieldOutput
from backend.domain.products.entities.yield_profile import YieldProfile
from backend.domain.products.entities.yield_profile_version import YieldProfileVersion
from backend.domain.products.recipe_enums import OutputType
from backend.infrastructure.db.repositories.products.yield_repository import (
    YieldRepository,
)
from backend.infrastructure.db.schema.products_schema import create_products_schema


@pytest.fixture
def repo():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_products_schema(c)
    for pid in ("canal", "lomo", "hueso"):
        c.execute("INSERT INTO products (id,code,name,name_normalized,product_type,"
                  "lifecycle_status,base_unit_id) VALUES (?,?,?,?,?,?,?)",
                  (pid, pid.upper(), pid, pid, "CARCASS", "ACTIVE", "kg"))
    c.commit()
    yield YieldRepository(c)
    c.close()


def _active(repo):
    p = YieldProfile(input_product_id="canal", name="Canal bovina", species_id="bov")
    repo.save_profile(p)
    v = YieldProfileVersion(yield_profile_id=p.id, version_number=1,
                            tolerance_pct=Decimal("2"))
    v.add_output(YieldOutput(product_id="lomo", output_type=OutputType.MAIN_PRODUCT,
                             expected_yield_pct=Decimal("70"), unit_id="kg",
                             minimum_yield_pct=Decimal("65"), cost_allocation_weight=Decimal("0.8")))
    v.add_output(YieldOutput(product_id="hueso", output_type=OutputType.BY_PRODUCT,
                             expected_yield_pct=Decimal("30"), unit_id="kg"))
    v.submit(); v.approve(approved_by_user_id="mgr"); v.activate()
    repo.save_version(v)
    return p, v


def test_version_round_trip(repo):
    _p, v = _active(repo)
    got = repo.get_version(v.id)
    assert got.status.value == "ACTIVE" and got.tolerance_pct == Decimal("2")
    assert len(got.outputs) == 2
    main = next(o for o in got.outputs if o.product_id == "lomo")
    assert main.minimum_yield_pct == Decimal("65")
    assert main.cost_allocation_weight == Decimal("0.8")


def test_active_version_for_input(repo):
    _active(repo)
    got = repo.active_version_for_input("canal")
    assert got is not None and got.total_expected_yield() == Decimal("100")


def test_absent_returns_none(repo):
    assert repo.active_version_for_input("nope") is None
    assert repo.get_profile("nope") is None
