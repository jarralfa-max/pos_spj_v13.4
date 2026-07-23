"""PROD-7 — barcodes/códigos: VO Barcode (checksum), scale barcode, unicidad."""

from decimal import Decimal

import pytest

from backend.domain.products.barcode_enums import BarcodeType
from backend.domain.products.entities.product_alternate_code import (
    ProductAlternateCode,
)
from backend.domain.products.entities.product_barcode import ProductBarcode
from backend.domain.products.exceptions import (
    BarcodeAlreadyAssignedError,
    InvalidBarcodeError,
    InvalidScaleBarcodeError,
    ProductsDomainError,
)
from backend.domain.products.policies.barcode_uniqueness_policy import (
    ensure_barcode_assignable,
)
from backend.domain.products.value_objects.barcode import Barcode, gs1_check_digit
from backend.domain.products.value_objects.scale_barcode import (
    ScaleBarcodeFormat,
    parse_scale_barcode,
)


# ── Barcode VO + checksum (§17) ──────────────────────────────────────────────
class TestBarcode:
    def test_valid_ean13(self):
        # 750102030405 + check digit
        body = "750102030405"
        code = body + str(gs1_check_digit(body))
        b = Barcode(value=code, barcode_type=BarcodeType.EAN)
        assert b.value == code

    def test_bad_ean_checksum_rejected(self):
        with pytest.raises(InvalidBarcodeError):
            Barcode(value="7501020304059", barcode_type=BarcodeType.EAN)  # wrong check

    def test_ean_wrong_length_rejected(self):
        with pytest.raises(InvalidBarcodeError):
            Barcode(value="12345", barcode_type=BarcodeType.EAN)

    def test_numeric_type_requires_digits(self):
        with pytest.raises(InvalidBarcodeError):
            Barcode(value="ABC", barcode_type=BarcodeType.PLU)

    def test_qr_stored_verbatim(self):
        b = Barcode(value="  product:123|lot:ABC  ", barcode_type=BarcodeType.QR)
        assert b.value == "product:123|lot:ABC"

    def test_empty_rejected(self):
        with pytest.raises(InvalidBarcodeError):
            Barcode(value="  ", barcode_type=BarcodeType.INTERNAL_SKU)

    def test_upc_a_valid(self):
        body = "03600029145"
        code = body + str(gs1_check_digit(body))
        assert Barcode(value=code, barcode_type=BarcodeType.UPC).value == code


# ── scale barcode (§12) ──────────────────────────────────────────────────────
class TestScaleBarcode:
    def _fmt(self, **kw):
        base = dict(prefix="2", plu_start=1, plu_length=5, value_start=6,
                    value_length=5, value_kind="WEIGHT", value_decimals=3)
        base.update(kw)
        return ScaleBarcodeFormat(**base)

    def test_parse_weight(self):
        # "2" + "12345"(plu) + "01500"(weight=1.500) + check
        reading = parse_scale_barcode("21234501500 7".replace(" ", ""), self._fmt())
        assert reading.plu == "12345"
        assert reading.value == Decimal("1.500")
        assert reading.value_kind == "WEIGHT"

    def test_wrong_prefix_rejected(self):
        with pytest.raises(InvalidScaleBarcodeError):
            parse_scale_barcode("31234501500", self._fmt())

    def test_non_numeric_rejected(self):
        with pytest.raises(InvalidScaleBarcodeError):
            parse_scale_barcode("2ABCDE", self._fmt())

    def test_too_short_rejected(self):
        with pytest.raises(InvalidScaleBarcodeError):
            parse_scale_barcode("2123", self._fmt())

    def test_price_kind(self):
        fmt = self._fmt(value_kind="PRICE", value_decimals=2)
        reading = parse_scale_barcode("21234509999", fmt)
        assert reading.value == Decimal("99.99") and reading.value_kind == "PRICE"

    def test_bad_format_rejected(self):
        with pytest.raises(InvalidScaleBarcodeError):
            ScaleBarcodeFormat(prefix="X", plu_start=0, plu_length=5,
                               value_start=5, value_length=5)


# ── entidades ────────────────────────────────────────────────────────────────
class TestEntities:
    def test_product_barcode_requires_product(self):
        with pytest.raises(InvalidBarcodeError):
            ProductBarcode(product_id="", barcode=Barcode("PLU1", BarcodeType.INTERNAL_SKU))

    def test_product_barcode_value_property(self):
        pb = ProductBarcode(product_id="p1",
                            barcode=Barcode("SKU-1", BarcodeType.INTERNAL_SKU))
        assert pb.value == "SKU-1"

    def test_alternate_code_requires_code(self):
        with pytest.raises(ProductsDomainError):
            ProductAlternateCode(product_id="p1", code="  ")


# ── uniqueness policy (§17) ──────────────────────────────────────────────────
class TestUniqueness:
    def test_free_barcode_assignable(self):
        ensure_barcode_assignable(barcode_value="X", product_id="p1",
                                  current_owner_product_id=None)

    def test_same_product_reassign_ok(self):
        ensure_barcode_assignable(barcode_value="X", product_id="p1",
                                  current_owner_product_id="p1")

    def test_other_product_rejected(self):
        with pytest.raises(BarcodeAlreadyAssignedError):
            ensure_barcode_assignable(barcode_value="X", product_id="p2",
                                      current_owner_product_id="p1")
