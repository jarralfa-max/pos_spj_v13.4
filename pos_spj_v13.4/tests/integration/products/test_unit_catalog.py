"""P0-03 — catálogo de unidades: seed migración 155 + UnitCatalogQueryService."""

import importlib
import sqlite3

import pytest

from backend.application.products.queries.unit_catalog_query_service import (
    UnitCatalogQueryService,
)
from backend.infrastructure.db.schema.products_schema import create_products_schema

_seed = importlib.import_module("migrations.standalone.155_products_seed_base_units")


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_products_schema(c)
    c.commit()
    yield c
    c.close()


def test_seed_creates_base_units(conn):
    _seed.run(conn)
    svc = UnitCatalogQueryService(conn)
    codes = {u["code"] for u in svc.list_units()}
    assert {"KG", "PZA", "LT", "CAJA"} <= codes
    kg = next(u for u in svc.list_units() if u["code"] == "KG")
    assert kg["dimension"] == "WEIGHT" and len(kg["id"]) == 36  # UUID, no el texto


def test_seed_idempotent(conn):
    _seed.run(conn)
    n1 = len(UnitCatalogQueryService(conn).list_units())
    _seed.run(conn)
    n2 = len(UnitCatalogQueryService(conn).list_units())
    assert n1 == n2 and n1 > 0


def test_unit_exists_only_for_real_id(conn):
    _seed.run(conn)
    svc = UnitCatalogQueryService(conn)
    kg_id = next(u["id"] for u in svc.list_units() if u["code"] == "KG")
    assert svc.unit_exists(kg_id)
    assert not svc.unit_exists("KG")  # el código NO es un id válido
    assert not svc.unit_exists("nope")


def test_list_filters_by_dimension(conn):
    _seed.run(conn)
    weights = UnitCatalogQueryService(conn).list_units(dimension="WEIGHT")
    assert all(u["dimension"] == "WEIGHT" for u in weights)
    assert {"KG", "G"} <= {u["code"] for u in weights}
