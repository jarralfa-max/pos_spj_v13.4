"""PROD-7 — persistencia de barcodes/códigos alternos + unicidad de activos."""

import sqlite3

import pytest

from backend.domain.products.barcode_enums import BarcodeType
from backend.domain.products.entities.product_alternate_code import (
    ProductAlternateCode,
)
from backend.domain.products.entities.product_barcode import ProductBarcode
from backend.domain.products.exceptions import BarcodeAlreadyAssignedError
from backend.domain.products.value_objects.barcode import Barcode
from backend.infrastructure.db.repositories.products.barcode_repository import (
    BarcodeRepository,
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
    yield BarcodeRepository(c)
    c.close()


def _bc(product_id, value, typ=BarcodeType.INTERNAL_SKU, **kw):
    return ProductBarcode(product_id=product_id, barcode=Barcode(value, typ), **kw)


def test_assign_and_list(repo):
    repo.assign(_bc("p1", "SKU-1", is_primary=True))
    repo.assign(_bc("p1", "SKU-2"))
    got = repo.list_for_product("p1")
    assert len(got) == 2 and got[0].is_primary  # primary first


def test_active_uniqueness_policy_blocks_other_product(repo):
    repo.assign(_bc("p1", "SHARED"))
    with pytest.raises(BarcodeAlreadyAssignedError):
        repo.assign(_bc("p2", "SHARED"))


def test_db_unique_index_backstop(repo):
    # incluso saltando la policy, el índice parcial UNIQUE bloquea duplicado activo
    repo.assign(_bc("p1", "DUP"))
    with pytest.raises(sqlite3.IntegrityError):
        repo._conn.execute(
            "INSERT INTO product_barcodes (id,product_id,barcode_value,barcode_type,"
            "is_primary,active) VALUES ('x','p2','DUP','INTERNAL_SKU',0,1)")


def test_find_by_value(repo):
    repo.assign(_bc("p1", "750102030405" + _check("750102030405"), BarcodeType.EAN))
    val = "750102030405" + _check("750102030405")
    found = repo.find_by_value(val)
    assert found and found.product_id == "p1"


def test_alternate_codes(repo):
    repo.add_alternate_code(ProductAlternateCode(product_id="p1", code="SUP-123",
                                                 supplier_id="s1"))
    codes = repo.list_alternate_codes("p1")
    assert len(codes) == 1 and codes[0].code == "SUP-123"


def _check(body):
    from backend.domain.products.value_objects.barcode import gs1_check_digit
    return str(gs1_check_digit(body))
