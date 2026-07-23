"""PROD-5 — persistencia de unidades/conversiones/peso-variable (round-trip Decimal)."""

import sqlite3
from decimal import Decimal

import pytest

from backend.domain.products.entities.product_unit_conversion import (
    ProductUnitConversion,
)
from backend.domain.products.entities.unit_of_measure import UnitOfMeasure
from backend.domain.products.unit_enums import PriceBasis, UnitDimension
from backend.domain.products.value_objects.catch_weight_configuration import (
    CatchWeightConfiguration,
)
from backend.infrastructure.db.repositories.products.unit_repository import UnitRepository
from backend.infrastructure.db.schema.products_schema import create_products_schema


@pytest.fixture
def repo():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_products_schema(c)
    c.execute("INSERT INTO products (id,code,name,name_normalized,product_type,"
              "lifecycle_status,base_unit_id) VALUES "
              "('p1','P1','P1','p1','GROUND_MEAT','ACTIVE','kg')")
    c.commit()
    yield UnitRepository(c)
    c.close()


def test_unit_round_trip(repo):
    repo.save_unit(UnitOfMeasure(code="KG", name="Kilogramo", dimension=UnitDimension.WEIGHT))
    repo.save_unit(UnitOfMeasure(code="PZA", name="Pieza", dimension=UnitDimension.COUNT))
    weights = repo.list_units(dimension=UnitDimension.WEIGHT)
    assert [u.code for u in weights] == ["KG"]
    assert len(repo.list_units()) == 2


def test_conversion_decimal_round_trip(repo):
    conv = ProductUnitConversion(from_unit_id="caja", to_unit_id="kg",
                                 factor=Decimal("20.5"), rounding_scale=3)
    repo.save_conversion(conv)
    got = repo.list_conversions()
    assert len(got) == 1
    assert got[0].factor == Decimal("20.5") and isinstance(got[0].factor, Decimal)


def test_product_specific_conversion_included(repo):
    repo.save_conversion(ProductUnitConversion(from_unit_id="a", to_unit_id="b",
                                               factor=Decimal("2")))  # global
    repo.save_conversion(ProductUnitConversion(product_id="p1", from_unit_id="c",
                                               to_unit_id="d", factor=Decimal("3")))
    assert len(repo.list_conversions(product_id="p1")) == 2
    assert len(repo.list_conversions()) == 1  # solo la global


def test_catch_weight_round_trip(repo):
    cfg = CatchWeightConfiguration(
        enabled=True, nominal_unit_id="pza", weight_unit_id="kg",
        minimum_weight=Decimal("1.0"), maximum_weight=Decimal("2.0"),
        average_weight=Decimal("1.5"), tolerance_pct=Decimal("5"),
        price_basis=PriceBasis.PER_KILOGRAM, scale_barcode_enabled=True)
    repo.save_catch_weight("p1", cfg)
    got = repo.get_catch_weight("p1")
    assert got.enabled and got.scale_barcode_enabled
    assert got.minimum_weight == Decimal("1.0") and got.maximum_weight == Decimal("2.0")
    assert got.price_basis is PriceBasis.PER_KILOGRAM

    def _upsert():
        cfg2 = CatchWeightConfiguration(
            enabled=True, nominal_unit_id="pza", weight_unit_id="kg",
            minimum_weight=Decimal("1.2"), maximum_weight=Decimal("2.4"))
        repo.save_catch_weight("p1", cfg2)
        assert repo.get_catch_weight("p1").maximum_weight == Decimal("2.4")

    _upsert()


def test_catch_weight_absent_returns_none(repo):
    assert repo.get_catch_weight("nope") is None
