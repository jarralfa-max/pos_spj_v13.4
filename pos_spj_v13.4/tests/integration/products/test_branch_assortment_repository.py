"""PROD-14 — persistencia de sucursales/surtidos (un producto, muchas sucursales)."""

import sqlite3

import pytest

from backend.domain.products.channel_enums import SalesChannel
from backend.domain.products.entities.assortment import Assortment, AssortmentProduct
from backend.domain.products.entities.branch_product import BranchProduct
from backend.infrastructure.db.repositories.products.branch_assortment_repository import (
    BranchAssortmentRepository,
)
from backend.infrastructure.db.schema.products_schema import create_products_schema


@pytest.fixture
def repo():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_products_schema(c)
    for pid in ("p1", "p2"):
        c.execute("INSERT INTO products (id,code,name,name_normalized,product_type,"
                  "lifecycle_status,base_unit_id) VALUES (?,?,?,?,?,?,?)",
                  (pid, pid.upper(), pid, pid, "RESALE_PRODUCT", "ACTIVE", "pza"))
    c.commit()
    yield BranchAssortmentRepository(c)
    c.close()


def test_one_product_many_branches(repo):
    repo.set_branch_product(BranchProduct(product_id="p1", branch_id="b1", enabled=True))
    repo.set_branch_product(BranchProduct(product_id="p1", branch_id="b2", enabled=False))
    assert repo.is_enabled_at_branch("p1", "b1")
    assert not repo.is_enabled_at_branch("p1", "b2")
    assert repo.products_at_branch("b1") == ["p1"]


def test_branch_product_upsert(repo):
    repo.set_branch_product(BranchProduct(product_id="p1", branch_id="b1", enabled=False))
    repo.set_branch_product(BranchProduct(product_id="p1", branch_id="b1", enabled=True))
    assert repo.is_enabled_at_branch("p1", "b1")


def test_disabled_or_absent_returns_false(repo):
    assert not repo.is_enabled_at_branch("p1", "nope")


def test_assortment_round_trip(repo):
    a = Assortment(name="POS Centro", channel=SalesChannel.POS, branch_id="b1")
    repo.save_assortment(a)
    repo.add_to_assortment(AssortmentProduct(assortment_id=a.id, product_id="p1"))
    repo.add_to_assortment(AssortmentProduct(assortment_id=a.id, product_id="p2", enabled=False))
    got = repo.get_assortment(a.id)
    assert got.channel is SalesChannel.POS
    assert repo.products_in_assortment(a.id) == ["p1"]
