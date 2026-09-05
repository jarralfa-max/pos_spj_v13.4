"""PROD-7 — códigos de barras, báscula, QR y códigos alternos.

Antes de esta fase, `BarcodeRepository.assign()` (unicidad activa vía
`barcode_uniqueness_policy`) existía completo pero su único consumidor era
una lectura (`active_owner`) en `product_query_service.py` — ningún caso de
uso real podía asignar un código de barras, de báscula, QR o alterno a un
producto. Estos tests prueban la cadena completa, incluida la unicidad
activa ejercida por primera vez a través de un caso de uso real.
"""

from __future__ import annotations

import sqlite3

import pytest

from backend.application.products.authorization.policy import ProductsAuthorizationPolicy
from backend.application.products.commands.product_barcode_commands import (
    AddAlternateCodeCommand,
    AssignBarcodeCommand,
    SetBarcodeActiveCommand,
)
from backend.application.products.permissions import ProductPermissions
from backend.application.products.use_cases.product_barcode_use_cases import (
    AddAlternateCodeUseCase,
    AssignBarcodeUseCase,
    SetBarcodeActiveUseCase,
)
from backend.domain.products.exceptions import ProductPermissionDeniedError
from backend.infrastructure.db.schema.products_schema import create_products_schema

_P = ProductPermissions


class _Checker:
    def __init__(self, granted):
        self._granted = set(granted)

    def has_permission(self, user_id, code):
        return code in self._granted


_ALL = ProductsAuthorizationPolicy(_Checker({
    _P.BARCODES_MANAGE, _P.ALTERNATE_CODES_MANAGE}))


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_products_schema(c)
    c.commit()
    yield c
    c.close()


def _assign(conn, product_id="prod-1", value="12345670", barcode_type="EAN", **kw):
    base = dict(operation_id="op", product_id=product_id, value=value,
               barcode_type=barcode_type, user_id="u1")
    base.update(kw)
    return AssignBarcodeUseCase(conn, _ALL).execute(AssignBarcodeCommand(**base))


class TestAssignBarcode:
    def test_assign_ean_with_valid_checksum(self, conn):
        # EAN-13 real (código de barras de ejemplo con dígito verificador OK)
        r = _assign(conn, value="4006381333931", barcode_type="EAN")
        assert r.success
        row = conn.execute("SELECT barcode_value, barcode_type FROM product_barcodes "
                           "WHERE id=?", (r.entity_id,)).fetchone()
        assert row["barcode_value"] == "4006381333931" and row["barcode_type"] == "EAN"

    def test_assign_bad_checksum_rejected(self, conn):
        r = _assign(conn, value="4006381333930", barcode_type="EAN")  # dígito incorrecto
        assert not r.success

    def test_assign_scale_barcode(self, conn):
        r = _assign(conn, value="2012345000009", barcode_type="SCALE_BARCODE")
        assert r.success

    def test_assign_qr_non_numeric(self, conn):
        r = _assign(conn, value="https://spj.mx/p/abc123", barcode_type="QR")
        assert r.success

    def test_duplicate_active_barcode_rejected_on_other_product(self, conn):
        _assign(conn, product_id="prod-1", value="4006381333931", barcode_type="EAN")
        r2 = _assign(conn, product_id="prod-2", value="4006381333931", barcode_type="EAN")
        assert not r2.success and "asignado" in r2.message.lower()

    def test_reassign_to_same_product_is_idempotent(self, conn):
        r1 = _assign(conn, product_id="prod-1", value="4006381333931", barcode_type="EAN")
        r2 = _assign(conn, product_id="prod-1", value="4006381333931", barcode_type="EAN")
        assert r1.success and r2.success

    def test_requires_permission(self, conn):
        no_perm = ProductsAuthorizationPolicy(_Checker(set()))
        with pytest.raises(ProductPermissionDeniedError):
            AssignBarcodeUseCase(conn, no_perm).execute(AssignBarcodeCommand(
                operation_id="op", product_id="prod-1", value="4006381333931",
                barcode_type="EAN"))

    def test_assignment_writes_audit_entry(self, conn):
        r = _assign(conn, value="4006381333931")
        row = conn.execute(
            "SELECT action FROM product_audit_log WHERE entity_id='prod-1'").fetchone()
        assert row["action"] == "PRODUCT_BARCODE_ASSIGNED"


class TestDeactivateBarcode:
    def test_deactivate_frees_value_for_reassignment(self, conn):
        r1 = _assign(conn, product_id="prod-1", value="4006381333931")
        SetBarcodeActiveUseCase(conn, _ALL).execute(SetBarcodeActiveCommand(
            operation_id="op2", barcode_id=r1.entity_id, active=False, user_id="u1"))
        # inactivo: ya no bloquea la reasignación a otro producto (§17)
        r2 = _assign(conn, product_id="prod-2", value="4006381333931")
        assert r2.success

    def test_deactivate_unknown_barcode(self, conn):
        r = SetBarcodeActiveUseCase(conn, _ALL).execute(SetBarcodeActiveCommand(
            operation_id="op", barcode_id="nope", active=False, user_id="u1"))
        assert not r.success


class TestAlternateCodes:
    def test_add_alternate_code(self, conn):
        r = AddAlternateCodeUseCase(conn, _ALL).execute(AddAlternateCodeCommand(
            operation_id="op", product_id="prod-1", code="SUP-000123",
            code_type="SUPPLIER_CODE", supplier_id="sup-1", user_id="u1"))
        assert r.success
        row = conn.execute("SELECT code, supplier_id FROM product_alternate_codes "
                           "WHERE id=?", (r.entity_id,)).fetchone()
        assert row["code"] == "SUP-000123" and row["supplier_id"] == "sup-1"

    def test_requires_permission(self, conn):
        no_perm = ProductsAuthorizationPolicy(_Checker(set()))
        with pytest.raises(ProductPermissionDeniedError):
            AddAlternateCodeUseCase(conn, no_perm).execute(AddAlternateCodeCommand(
                operation_id="op", product_id="prod-1", code="X"))
