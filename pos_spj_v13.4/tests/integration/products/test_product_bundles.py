"""Combos/kits — capa de aplicación: crear/editar/lifecycle + validación."""

import sqlite3

import pytest

from backend.application.products.authorization.policy import ProductsAuthorizationPolicy
from backend.application.products.commands.product_bundle_commands import (
    BundleVersionTransitionCommand,
    CreateBundleCommand,
    UpdateBundleVersionCommand,
)
from backend.application.products.permissions import ProductPermissions
from backend.application.products.queries.product_bundle_query_service import (
    ProductBundleQueryService,
)
from backend.application.products.use_cases.product_bundle_use_cases import (
    ActivateBundleVersionUseCase,
    ApproveBundleVersionUseCase,
    CreateProductBundleUseCase,
    SubmitBundleVersionUseCase,
    UpdateBundleVersionUseCase,
)
from backend.domain.products.exceptions import (
    BundleCycleDetectedError,
    ProductPermissionDeniedError,
)
from backend.infrastructure.db.schema.products_schema import create_products_schema

_BUNDLE = "combo-1"
_UNIT = "unit-pza"


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_products_schema(c)
    yield c
    c.close()


class _Checker:
    def __init__(self, granted):
        self._granted = set(granted)

    def has_permission(self, user_id, code):
        return code in self._granted


_MANAGE = ProductsAuthorizationPolicy(_Checker({ProductPermissions.BUNDLES_MANAGE}))

_COMPONENTS = [
    {"component_product_id": "refresco", "quantity": "1", "unit_id": _UNIT},
    {"component_product_id": "hamburguesa", "quantity": "1", "unit_id": _UNIT},
]


def _create(conn, auth=None, components=None):
    return CreateProductBundleUseCase(conn, auth or _MANAGE).execute(
        CreateBundleCommand(
            operation_id="op", product_id=_BUNDLE, bundle_type="FIXED_COMBO",
            name="Combo del día", components=components or _COMPONENTS, user_id="u1"))


def test_create_bundle_with_draft_version(conn):
    r = _create(conn)
    assert r.success and r.bundle_id and r.version_id
    v = conn.execute("SELECT status FROM bundle_versions WHERE id=?",
                     (r.version_id,)).fetchone()
    assert v["status"] == "DRAFT"
    n = conn.execute("SELECT COUNT(*) AS n FROM bundle_components WHERE version_id=?",
                     (r.version_id,)).fetchone()["n"]
    assert n == 2


def test_create_requires_permission(conn):
    auth = ProductsAuthorizationPolicy(_Checker(set()))
    with pytest.raises(ProductPermissionDeniedError):
        _create(conn, auth=auth)


def test_create_rejects_self_containment(conn):
    r = _create(conn, components=[{"component_product_id": _BUNDLE, "quantity": "1",
                                   "unit_id": _UNIT}])
    assert not r.success and "propio" in r.message.lower()


def test_create_rejects_duplicate_components(conn):
    r = _create(conn, components=[
        {"component_product_id": "x", "quantity": "1", "unit_id": _UNIT},
        {"component_product_id": "x", "quantity": "2", "unit_id": _UNIT}])
    assert not r.success and "repetir" in r.message.lower()


def test_create_emits_event(conn):
    r = _create(conn)
    row = conn.execute("SELECT event_name FROM product_outbox WHERE entity_id=?",
                       (r.bundle_id,)).fetchone()
    assert row["event_name"] == "PRODUCT_BUNDLE_CREATED"


def test_update_draft_replaces_components(conn):
    r = _create(conn)
    u = UpdateBundleVersionUseCase(conn, _MANAGE).execute(UpdateBundleVersionCommand(
        operation_id="op2", version_id=r.version_id,
        components=[{"component_product_id": "solo", "quantity": "3", "unit_id": _UNIT}],
        user_id="u1"))
    assert u.success
    n = conn.execute("SELECT COUNT(*) AS n FROM bundle_components WHERE version_id=?",
                     (r.version_id,)).fetchone()["n"]
    assert n == 1


def test_full_lifecycle(conn):
    r = _create(conn)
    for uc in (SubmitBundleVersionUseCase, ApproveBundleVersionUseCase,
               ActivateBundleVersionUseCase):
        assert uc(conn, _MANAGE).execute(BundleVersionTransitionCommand(
            operation_id=f"t{uc.__name__}", version_id=r.version_id,
            user_id="u1")).success
    assert conn.execute("SELECT status FROM bundle_versions WHERE id=?",
                        (r.version_id,)).fetchone()["status"] == "ACTIVE"


def test_query_lists_bundles_and_detail(conn):
    r = _create(conn)
    q = ProductBundleQueryService(conn)
    bundles = q.list_bundles(_BUNDLE)
    assert bundles[0]["name"] == "Combo del día"
    versions = q.list_versions(r.bundle_id)
    assert versions[0]["version_number"] == 1
    detail = q.version_detail(r.version_id)
    assert {c["component_product_id"] for c in detail["components"]} == {
        "refresco", "hamburguesa"}


def test_cycle_error_is_domain():
    assert issubclass(BundleCycleDetectedError, Exception)
