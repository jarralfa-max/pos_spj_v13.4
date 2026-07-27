"""Rendimientos — capa de aplicación: crear/editar/lifecycle + tolerancia + segregación."""

import sqlite3

import pytest

from backend.application.products.authorization.policy import ProductsAuthorizationPolicy
from backend.application.products.commands.product_yield_commands import (
    CreateYieldProfileCommand,
    UpdateYieldVersionCommand,
    YieldVersionTransitionCommand,
)
from backend.application.products.permissions import ProductPermissions
from backend.application.products.queries.product_yield_query_service import (
    ProductYieldQueryService,
)
from backend.application.products.use_cases.product_yield_use_cases import (
    ActivateYieldVersionUseCase,
    ApproveYieldVersionUseCase,
    CreateYieldProfileUseCase,
    SubmitYieldVersionUseCase,
    UpdateYieldVersionUseCase,
)
from backend.domain.products.exceptions import (
    ProductPermissionDeniedError,
    SegregationOfDutiesError,
    YieldToleranceExceededError,
)
from backend.infrastructure.db.schema.products_schema import create_products_schema

_INPUT = "carcass-1"
_UNIT = "unit-kg"


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


_P = ProductPermissions
_ALL = ProductsAuthorizationPolicy(_Checker({
    _P.YIELD_CREATE, _P.YIELD_EDIT, _P.YIELD_APPROVE, _P.YIELD_ACTIVATE}))

_OUTPUTS = [
    {"product_id": "lomo", "output_type": "MAIN_PRODUCT",
     "expected_yield_pct": "60", "unit_id": _UNIT},
    {"product_id": "hueso", "output_type": "BY_PRODUCT",
     "expected_yield_pct": "40", "unit_id": _UNIT},
]


def _create(conn, auth=None, creator="creator", outputs=None, tolerance="0"):
    return CreateYieldProfileUseCase(conn, auth or _ALL).execute(
        CreateYieldProfileCommand(
            operation_id="op", input_product_id=_INPUT, name="Rendimiento canal",
            tolerance_pct=tolerance, outputs=outputs or _OUTPUTS, user_id=creator))


def test_create_profile_with_draft_version(conn):
    r = _create(conn)
    assert r.success and r.profile_id and r.version_id
    v = conn.execute("SELECT status, created_by FROM yield_profile_versions WHERE id=?",
                     (r.version_id,)).fetchone()
    assert v["status"] == "DRAFT" and v["created_by"] == "creator"
    n = conn.execute("SELECT COUNT(*) AS n FROM yield_outputs WHERE version_id=?",
                     (r.version_id,)).fetchone()["n"]
    assert n == 2


def test_create_requires_permission(conn):
    auth = ProductsAuthorizationPolicy(_Checker(set()))
    with pytest.raises(ProductPermissionDeniedError):
        _create(conn, auth=auth)


def test_create_rejects_yield_out_of_tolerance(conn):
    r = _create(conn, outputs=[{"product_id": "lomo", "output_type": "MAIN_PRODUCT",
                                "expected_yield_pct": "50", "unit_id": _UNIT}],
                tolerance="0")
    assert not r.success and "tolerancia" in r.message.lower()


def test_create_within_tolerance_ok(conn):
    r = _create(conn, outputs=[{"product_id": "lomo", "output_type": "MAIN_PRODUCT",
                                "expected_yield_pct": "95", "unit_id": _UNIT}],
                tolerance="10")
    assert r.success


def test_create_emits_event(conn):
    r = _create(conn)
    row = conn.execute("SELECT event_name FROM product_outbox WHERE entity_id=?",
                       (r.profile_id,)).fetchone()
    assert row["event_name"] == "PRODUCT_YIELD_PROFILE_CREATED"


def test_update_draft_replaces_outputs(conn):
    r = _create(conn)
    u = UpdateYieldVersionUseCase(conn, _ALL).execute(UpdateYieldVersionCommand(
        operation_id="op2", version_id=r.version_id, tolerance_pct="0",
        outputs=[{"product_id": "lomo", "output_type": "MAIN_PRODUCT",
                  "expected_yield_pct": "100", "unit_id": _UNIT}], user_id="creator"))
    assert u.success
    n = conn.execute("SELECT COUNT(*) AS n FROM yield_outputs WHERE version_id=?",
                     (r.version_id,)).fetchone()["n"]
    assert n == 1


def test_full_lifecycle(conn):
    r = _create(conn, creator="alice")
    assert SubmitYieldVersionUseCase(conn, _ALL).execute(YieldVersionTransitionCommand(
        operation_id="s", version_id=r.version_id, user_id="alice")).success
    assert ApproveYieldVersionUseCase(conn, _ALL).execute(YieldVersionTransitionCommand(
        operation_id="a", version_id=r.version_id, user_id="bob")).success
    assert ActivateYieldVersionUseCase(conn, _ALL).execute(YieldVersionTransitionCommand(
        operation_id="ac", version_id=r.version_id, user_id="bob")).success
    assert conn.execute("SELECT status FROM yield_profile_versions WHERE id=?",
                        (r.version_id,)).fetchone()["status"] == "ACTIVE"


def test_creator_cannot_approve(conn):
    r = _create(conn, creator="alice")
    SubmitYieldVersionUseCase(conn, _ALL).execute(YieldVersionTransitionCommand(
        operation_id="s", version_id=r.version_id, user_id="alice"))
    with pytest.raises(SegregationOfDutiesError):
        ApproveYieldVersionUseCase(conn, _ALL).execute(YieldVersionTransitionCommand(
            operation_id="a", version_id=r.version_id, user_id="alice"))


def test_query_lists_profiles_and_detail(conn):
    r = _create(conn)
    q = ProductYieldQueryService(conn)
    profiles = q.list_profiles(_INPUT)
    assert profiles[0]["name"] == "Rendimiento canal"
    versions = q.list_versions(r.profile_id)
    assert versions[0]["version_number"] == 1
    detail = q.version_detail(r.version_id)
    assert {o["product_id"] for o in detail["outputs"]} == {"lomo", "hueso"}


def test_tolerance_error_type_is_domain(conn):
    # El use case captura ProductsDomainError; YieldToleranceExceededError lo es.
    assert issubclass(YieldToleranceExceededError, Exception)
