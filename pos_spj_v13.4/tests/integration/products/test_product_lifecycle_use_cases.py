"""P0-01/02/05 — ciclo de vida del maestro: lifecycle + autorización + completitud."""

import sqlite3

import pytest

from backend.application.products.authorization.policy import ProductsAuthorizationPolicy
from backend.application.products.commands.product_master_commands import (
    CreateProductMasterCommand,
)
from backend.application.products.permissions import ProductPermissions
from backend.application.products.queries.product_activation_readiness_query_service import (
    ProductActivationReadinessQueryService,
)
from backend.application.products.use_cases.product_lifecycle_use_cases import (
    ActivateProductUseCase,
    SubmitProductUseCase,
)
from backend.application.products.use_cases.product_master_use_cases import (
    CreateProductMasterUseCase,
)
from backend.infrastructure.db.schema.products_schema import create_products_schema

_UNIT = "unit-kg-0001"


class _Checker:
    """PermissionChecker de prueba: concede sólo los permisos dados."""
    def __init__(self, perms):
        self._perms = set(perms)

    def has_permission(self, user_id, code):
        return code in self._perms


_ALL = ProductsAuthorizationPolicy(_Checker({
    ProductPermissions.CREATE, ProductPermissions.OVERRIDE_CODE,
    ProductPermissions.SUBMIT, ProductPermissions.ACTIVATE}))


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_products_schema(c)
    c.execute("INSERT INTO units_of_measure (id, code, name, dimension, active) "
              "VALUES (?, 'KG', 'Kilogramo', 'WEIGHT', 1)", (_UNIT,))
    c.commit()
    yield c
    c.close()


def _new(conn, *, creator="creator", **kw):
    base = dict(operation_id="op", code="A-1", name="Bistec", product_type="RAW_MATERIAL",
                base_unit_id=_UNIT, category_id="cat1", user_id=creator)
    base.update(kw)
    return CreateProductMasterUseCase(conn, _ALL).execute(
        CreateProductMasterCommand(**base)).product_id


def test_full_flow_draft_review_active(conn):
    pid = _new(conn)
    assert SubmitProductUseCase(conn, _ALL).execute(product_id=pid, user_id="rev").status \
        == "UNDER_REVIEW"
    r = ActivateProductUseCase(conn, _ALL).execute(product_id=pid, user_id="approver")
    assert r.success and r.status == "ACTIVE"


def test_cannot_activate_from_draft(conn):
    pid = _new(conn)
    r = ActivateProductUseCase(conn, _ALL).execute(product_id=pid, user_id="approver")
    assert not r.success  # DRAFT → ACTIVE no permitido (falta submit)


def test_activate_incomplete_fails(conn):
    pid = _new(conn, category_id=None)
    SubmitProductUseCase(conn, _ALL).execute(product_id=pid, user_id="rev")
    r = ActivateProductUseCase(conn, _ALL).execute(product_id=pid, user_id="approver")
    assert not r.success and "faltan datos" in r.message.lower()


def test_segregation_creator_cannot_activate(conn):
    from backend.domain.products.exceptions import SegregationOfDutiesError
    pid = _new(conn, creator="alice")
    SubmitProductUseCase(conn, _ALL).execute(product_id=pid, user_id="alice")
    with pytest.raises(SegregationOfDutiesError):  # segundo par de ojos (§39)
        ActivateProductUseCase(conn, _ALL).execute(product_id=pid, user_id="alice")


def test_authorization_denied_without_permission(conn):
    from backend.domain.products.exceptions import ProductPermissionDeniedError
    pid = _new(conn)
    policy = ProductsAuthorizationPolicy(_Checker({ProductPermissions.CREATE}))  # sin SUBMIT
    with pytest.raises(ProductPermissionDeniedError):  # fail-closed
        SubmitProductUseCase(conn, policy).execute(product_id=pid, user_id="u")


def test_create_denied_without_create_permission(conn):
    from backend.domain.products.exceptions import ProductPermissionDeniedError
    policy = ProductsAuthorizationPolicy(_Checker(set()))
    with pytest.raises(ProductPermissionDeniedError):  # fail-closed
        CreateProductMasterUseCase(conn, policy).execute(CreateProductMasterCommand(
            operation_id="op", code="X-1", name="X", product_type="RAW_MATERIAL",
            base_unit_id=_UNIT, user_id="u"))


def test_readiness_reports_missing(conn):
    pid = _new(conn, code="M-2", category_id=None)
    ready = ProductActivationReadinessQueryService(conn).readiness(pid)
    assert not ready.ready and any("Categoría" in m for m in ready.missing)
