"""PROD-15 — persistencia de catálogos externos + matching por lookups del repo."""

import sqlite3

import pytest

from backend.domain.products.entities.external_catalog_source import (
    ExternalCatalogSource,
)
from backend.domain.products.entities.external_product_record import (
    ExternalProductRecord,
)
from backend.domain.products.entities.product_import_batch import ProductImportBatch
from backend.domain.products.external_enums import (
    ExternalProviderType,
    ExternalRecordStatus,
)
from backend.domain.products.services.product_matching_service import (
    ProductMatchingService,
)
from backend.infrastructure.db.repositories.products.external_catalog_repository import (
    ExternalCatalogRepository,
)
from backend.infrastructure.db.schema.products_schema import create_products_schema


@pytest.fixture
def repo():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_products_schema(c)
    c.execute("INSERT INTO products (id,code,name,name_normalized,product_type,"
              "lifecycle_status,base_unit_id) VALUES "
              "('prod-1','P1','Refresco Cola','refresco cola','RESALE_PRODUCT','ACTIVE','pza')")
    c.execute("INSERT INTO product_barcodes (id,product_id,barcode_value,barcode_type,"
              "is_primary,active) VALUES ('b1','prod-1','750','EAN',1,1)")
    c.commit()
    yield ExternalCatalogRepository(c)
    c.close()


def _source(repo):
    s = ExternalCatalogSource(code="OFF", name="Open Food Facts",
                              provider_type=ExternalProviderType.OPEN_FOOD_FACTS)
    repo.save_source(s)
    return s


def test_source_round_trip(repo):
    s = _source(repo)
    assert repo.get_source(s.id).code == "OFF"


def test_record_round_trip_and_provenance(repo):
    s = _source(repo)
    r = ExternalProductRecord(source_id=s.id, external_id="e1", name="Cola", barcode="750")
    repo.save_record(r)
    got = repo.get_record(r.id)
    assert got.source_id == s.id and got.data_quality_score.value > 0


def test_matching_via_repo_lookups(repo):
    s = _source(repo)
    r = ExternalProductRecord(source_id=s.id, external_id="e1", name="Cola", barcode="750")
    hit = ProductMatchingService().match(
        r, by_barcode=repo.barcode_lookup(), by_normalized_name=repo.name_lookup())
    assert hit == "prod-1"   # matched by barcode


def test_matching_by_name(repo):
    s = _source(repo)
    r = ExternalProductRecord(source_id=s.id, external_id="e2", name="Refresco Cola")
    hit = ProductMatchingService().match(
        r, by_barcode=repo.barcode_lookup(), by_normalized_name=repo.name_lookup())
    assert hit == "prod-1"   # matched by normalized name


def test_records_for_source_filter(repo):
    s = _source(repo)
    r = ExternalProductRecord(source_id=s.id, external_id="e1", name="Cola")
    r.approve()
    repo.save_record(r)
    approved = repo.records_for_source(s.id, status=ExternalRecordStatus.APPROVED)
    assert len(approved) == 1


def test_batch_finalize_round_trip(repo):
    s = _source(repo)
    b = ProductImportBatch(source_id=s.id, total_records=10, imported_records=8,
                           failed_records=2, created_by="u1")
    b.finalize()
    repo.save_batch(b)
    got = repo.get_batch(b.id)
    assert got.status.value == "PARTIAL" and got.imported_records == 8
