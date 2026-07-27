"""Despiece — capa de aplicación: crear/editar/lifecycle + validación."""

import sqlite3

import pytest

from backend.application.products.authorization.policy import ProductsAuthorizationPolicy
from backend.application.products.commands.product_cutting_commands import (
    CreateCuttingSchemeCommand,
    CuttingVersionTransitionCommand,
    UpdateCuttingVersionCommand,
)
from backend.application.products.permissions import ProductPermissions
from backend.application.products.queries.product_cutting_query_service import (
    ProductCuttingQueryService,
)
from backend.application.products.use_cases.product_cutting_use_cases import (
    ActivateCuttingVersionUseCase,
    ApproveCuttingVersionUseCase,
    CreateCuttingSchemeUseCase,
    SubmitCuttingVersionUseCase,
    UpdateCuttingVersionUseCase,
)
from backend.domain.products.exceptions import (
    CuttingSchemeCycleDetectedError,
    ProductPermissionDeniedError,
)
from backend.infrastructure.db.schema.products_schema import create_products_schema

_INPUT = "canal-1"
_SPECIES = "bovino"
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


_MANAGE = ProductsAuthorizationPolicy(
    _Checker({ProductPermissions.CUTTING_SCHEME_MANAGE}))

_OUTPUTS = [
    {"product_id": "lomo", "measure_kind": "BY_WEIGHT", "quantity": "10",
     "unit_id": _UNIT, "output_type": "MAIN_PRODUCT"},
    {"product_id": "costilla", "measure_kind": "BY_WEIGHT", "quantity": "5",
     "unit_id": _UNIT, "output_type": "CO_PRODUCT"},
]


def _create(conn, auth=None, outputs=None):
    return CreateCuttingSchemeUseCase(conn, auth or _MANAGE).execute(
        CreateCuttingSchemeCommand(
            operation_id="op", input_product_id=_INPUT, species_id=_SPECIES,
            name="Despiece canal", cut_level="PRIMARY",
            outputs=outputs or _OUTPUTS, user_id="u1"))


def test_create_scheme_with_draft_version(conn):
    r = _create(conn)
    assert r.success and r.scheme_id and r.version_id
    v = conn.execute("SELECT status FROM cutting_scheme_versions WHERE id=?",
                     (r.version_id,)).fetchone()
    assert v["status"] == "DRAFT"
    n = conn.execute("SELECT COUNT(*) AS n FROM cutting_outputs WHERE version_id=?",
                     (r.version_id,)).fetchone()["n"]
    assert n == 2


def test_create_requires_permission(conn):
    auth = ProductsAuthorizationPolicy(_Checker(set()))
    with pytest.raises(ProductPermissionDeniedError):
        _create(conn, auth=auth)


def test_create_rejects_self_containment(conn):
    r = _create(conn, outputs=[{"product_id": _INPUT, "measure_kind": "BY_WEIGHT",
                                "quantity": "1", "unit_id": _UNIT}])
    assert not r.success and "sí mismo" in r.message.lower()


def test_create_emits_event(conn):
    r = _create(conn)
    row = conn.execute("SELECT event_name FROM product_outbox WHERE entity_id=?",
                       (r.scheme_id,)).fetchone()
    assert row["event_name"] == "PRODUCT_CUTTING_SCHEME_CREATED"


def test_update_draft_replaces_outputs(conn):
    r = _create(conn)
    u = UpdateCuttingVersionUseCase(conn, _MANAGE).execute(UpdateCuttingVersionCommand(
        operation_id="op2", version_id=r.version_id,
        outputs=[{"product_id": "lomo", "measure_kind": "BY_PIECE", "quantity": "3",
                  "unit_id": _UNIT}], user_id="u1"))
    assert u.success
    n = conn.execute("SELECT COUNT(*) AS n FROM cutting_outputs WHERE version_id=?",
                     (r.version_id,)).fetchone()["n"]
    assert n == 1


def test_full_lifecycle(conn):
    r = _create(conn)
    for uc in (SubmitCuttingVersionUseCase, ApproveCuttingVersionUseCase,
               ActivateCuttingVersionUseCase):
        assert uc(conn, _MANAGE).execute(CuttingVersionTransitionCommand(
            operation_id=f"t{uc.__name__}", version_id=r.version_id,
            user_id="u1")).success
    assert conn.execute("SELECT status FROM cutting_scheme_versions WHERE id=?",
                        (r.version_id,)).fetchone()["status"] == "ACTIVE"


def test_query_lists_schemes_and_detail(conn):
    r = _create(conn)
    q = ProductCuttingQueryService(conn)
    schemes = q.list_schemes(_INPUT)
    assert schemes[0]["name"] == "Despiece canal"
    versions = q.list_versions(r.scheme_id)
    assert versions[0]["version_number"] == 1
    detail = q.version_detail(r.version_id)
    assert {o["product_id"] for o in detail["outputs"]} == {"lomo", "costilla"}


def test_cycle_error_is_domain():
    assert issubclass(CuttingSchemeCycleDetectedError, Exception)
