"""PROD-13 — persistencia de combos versionados + resolver de ciclos."""

import sqlite3
from decimal import Decimal

import pytest

from backend.domain.products.bundle_enums import BundleType
from backend.domain.products.entities.bundle_component import BundleComponent
from backend.domain.products.entities.bundle_version import BundleVersion
from backend.domain.products.entities.product_bundle import ProductBundle
from backend.infrastructure.db.repositories.products.bundle_repository import (
    BundleRepository,
)
from backend.infrastructure.db.schema.products_schema import create_products_schema


@pytest.fixture
def repo():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_products_schema(c)
    for pid in ("caja", "bistec", "chorizo"):
        c.execute("INSERT INTO products (id,code,name,name_normalized,product_type,"
                  "lifecycle_status,base_unit_id) VALUES (?,?,?,?,?,?,?)",
                  (pid, pid.upper(), pid, pid, "VIRTUAL_BUNDLE", "ACTIVE", "kg"))
    c.commit()
    yield BundleRepository(c)
    c.close()


def _active(repo):
    b = ProductBundle(product_id="caja", bundle_type=BundleType.MEAT_BOX,
                      name="Caja parrillera")
    repo.save_bundle(b)
    v = BundleVersion(bundle_id=b.id, version_number=1)
    v.add_component(BundleComponent(component_product_id="bistec", quantity=Decimal("1"),
                                    unit_id="kg"))
    v.add_component(BundleComponent(component_product_id="chorizo", quantity=Decimal("0.5"),
                                    unit_id="kg", optional=True))
    v.submit(); v.approve(approved_by_user_id="mgr"); v.activate()
    repo.save_version(v)
    return b, v


def test_version_round_trip(repo):
    _b, v = _active(repo)
    got = repo.get_version(v.id)
    assert got.status.value == "ACTIVE" and len(got.components) == 2
    chorizo = next(c for c in got.components if c.component_product_id == "chorizo")
    assert chorizo.optional and chorizo.quantity == Decimal("0.5")


def test_active_version_and_resolver(repo):
    _active(repo)
    assert repo.active_version_for_product("caja") is not None
    assert set(repo.component_resolver()("caja")) == {"bistec", "chorizo"}
    assert repo.component_resolver()("bistec") == []


def test_bundle_round_trip(repo):
    b, _v = _active(repo)
    got = repo.get_bundle(b.id)
    assert got.bundle_type is BundleType.MEAT_BOX and got.is_virtual
