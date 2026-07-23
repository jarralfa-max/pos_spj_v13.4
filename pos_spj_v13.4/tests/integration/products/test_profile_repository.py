"""PROD-8 — persistencia de perfiles calidad/vida útil/logística (round-trip Decimal)."""

import sqlite3
from decimal import Decimal

import pytest

from backend.domain.products.entities.product_logistics_profile import (
    ProductLogisticsProfile,
)
from backend.domain.products.entities.product_quality_profile import (
    ProductQualityProfile,
)
from backend.domain.products.entities.product_shelf_life_profile import (
    ProductShelfLifeProfile,
)
from backend.domain.products.value_objects.temperature_range import TemperatureRange
from backend.infrastructure.db.repositories.products.profile_repository import (
    ProfileRepository,
)
from backend.infrastructure.db.schema.products_schema import create_products_schema


@pytest.fixture
def repo():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_products_schema(c)
    c.execute("INSERT INTO products (id,code,name,name_normalized,product_type,"
              "lifecycle_status,base_unit_id) VALUES "
              "('p1','P1','P1','p1','PRIMARY_CUT','ACTIVE','kg')")
    c.commit()
    yield ProfileRepository(c)
    c.close()


def test_shelf_life_round_trip(repo):
    repo.save_shelf_life(ProductShelfLifeProfile(
        product_id="p1", shelf_life_days=30, minimum_remaining_for_receipt=20,
        minimum_remaining_for_sale=5, storage_condition="CHILLED"))
    got = repo.get_shelf_life("p1")
    assert got.shelf_life_days == 30 and got.storage_condition == "CHILLED"
    assert repo.has_shelf_life("p1") and not repo.has_shelf_life("nope")


def test_quality_round_trip(repo):
    repo.save_quality(ProductQualityProfile(
        product_id="p1", inspection_required=True, quarantine_required=True,
        fat_pct_min=Decimal("10"), fat_pct_max=Decimal("22.5")))
    got = repo.get_quality("p1")
    assert got.inspection_required and got.quarantine_required
    assert got.fat_pct_max == Decimal("22.5") and isinstance(got.fat_pct_max, Decimal)


def test_logistics_round_trip_with_temp(repo):
    repo.save_logistics(ProductLogisticsProfile(
        product_id="p1", gross_weight=Decimal("1.250"), net_weight=Decimal("1.000"),
        frozen=True,
        storage_temperature=TemperatureRange(Decimal("-20"), Decimal("-18"))))
    got = repo.get_logistics("p1")
    assert got.requires_cold_chain and got.frozen
    assert got.gross_weight == Decimal("1.250")
    assert got.storage_temperature.minimum == Decimal("-20")


def test_absent_profiles_return_none(repo):
    assert repo.get_quality("nope") is None
    assert repo.get_logistics("nope") is None
