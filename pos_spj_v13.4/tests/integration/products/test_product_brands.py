"""P1-02 — catálogo de marcas: alta/edición/activación + query service."""

import json
import sqlite3

import pytest

from backend.application.products.authorization.policy import ProductsAuthorizationPolicy
from backend.application.products.commands.product_brand_commands import (
    CreateBrandCommand,
    SetBrandActiveCommand,
    UpdateBrandCommand,
)
from backend.application.products.permissions import ProductPermissions
from backend.application.products.queries.product_brand_query_service import (
    ProductBrandQueryService,
)
from backend.application.products.use_cases.product_brand_use_cases import (
    CreateProductBrandUseCase,
    SetProductBrandActiveUseCase,
    UpdateProductBrandUseCase,
)
from backend.domain.products.entities.brand import Brand
from backend.domain.products.exceptions import (
    InvalidBrandError,
    ProductPermissionDeniedError,
)
from backend.infrastructure.db.schema.products_schema import create_products_schema


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


_MANAGE = ProductsAuthorizationPolicy(_Checker({ProductPermissions.BRANDS_MANAGE}))


def _create(conn, code, name, auth=None, **kw):
    return CreateProductBrandUseCase(conn, auth or _MANAGE).execute(
        CreateBrandCommand(operation_id="op", code=code, name=name, user_id="u1", **kw))


# ── entidad ──────────────────────────────────────────────────────────────────
def test_entity_requires_code_and_name():
    with pytest.raises(InvalidBrandError):
        Brand(code="", name="Bimbo")
    with pytest.raises(InvalidBrandError):
        Brand(code="BIM", name="")


def test_entity_uppercases_code_and_trims_description():
    b = Brand(code="bim", name="  Bimbo  ", description="  pan  ")
    assert b.code == "BIM" and b.name == "Bimbo" and b.description == "pan"
    assert b.name_normalized == "bimbo"
    assert Brand(code="X", name="Y", description="   ").description is None


# ── alta ─────────────────────────────────────────────────────────────────────
def test_create_writes_brand(conn):
    r = _create(conn, "BIM", "Bimbo", description="Panadería")
    assert r.success and r.brand_id
    row = conn.execute("SELECT * FROM product_brands WHERE id=?",
                       (r.brand_id,)).fetchone()
    assert row["code"] == "BIM" and row["name"] == "Bimbo"
    assert row["name_normalized"] == "bimbo" and row["description"] == "Panadería"
    assert row["active"] == 1


def test_create_rejects_duplicate_code(conn):
    _create(conn, "BIM", "Bimbo")
    r = _create(conn, "BIM", "Otra")
    assert not r.success and "ya existe" in r.message


def test_create_requires_manage_permission(conn):
    auth = ProductsAuthorizationPolicy(_Checker(set()))
    with pytest.raises(ProductPermissionDeniedError):
        _create(conn, "BIM", "Bimbo", auth=auth)


def test_create_is_uuid_and_emits_event(conn):
    r = _create(conn, "BIM", "Bimbo")
    assert "-" in r.brand_id and len(r.brand_id) == 36
    row = conn.execute("SELECT event_name, payload FROM product_outbox WHERE entity_id=?",
                       (r.brand_id,)).fetchone()
    assert row["event_name"] == "PRODUCT_BRAND_CREATED"
    assert json.loads(row["payload"])["code"] == "BIM"


# ── edición ──────────────────────────────────────────────────────────────────
def test_update_changes_fields(conn):
    r = _create(conn, "BIM", "Bimbo")
    u = UpdateProductBrandUseCase(conn, _MANAGE).execute(UpdateBrandCommand(
        operation_id="op2", brand_id=r.brand_id, code="BIMBO", name="Grupo Bimbo",
        description="Alimentos", user_id="u1"))
    assert u.success
    row = conn.execute("SELECT code, name, description FROM product_brands WHERE id=?",
                       (r.brand_id,)).fetchone()
    assert row["code"] == "BIMBO" and row["name"] == "Grupo Bimbo"
    assert row["description"] == "Alimentos"


def test_update_rejects_code_collision(conn):
    a = _create(conn, "BIM", "Bimbo")
    b = _create(conn, "LAL", "Lala")
    u = UpdateProductBrandUseCase(conn, _MANAGE).execute(UpdateBrandCommand(
        operation_id="op3", brand_id=b.brand_id, code="BIM", name="Lala",
        user_id="u1"))
    assert not u.success and "ya existe" in u.message


def test_update_unknown_brand(conn):
    u = UpdateProductBrandUseCase(conn, _MANAGE).execute(UpdateBrandCommand(
        operation_id="op4", brand_id="nope", code="X", name="X", user_id="u1"))
    assert not u.success and "no existe" in u.message


# ── activación ───────────────────────────────────────────────────────────────
def test_deactivate_and_reactivate(conn):
    r = _create(conn, "BIM", "Bimbo")
    d = SetProductBrandActiveUseCase(conn, _MANAGE).execute(SetBrandActiveCommand(
        operation_id="op5", brand_id=r.brand_id, active=False, user_id="u1"))
    assert d.success
    assert conn.execute("SELECT active FROM product_brands WHERE id=?",
                        (r.brand_id,)).fetchone()["active"] == 0
    q = ProductBrandQueryService(conn)
    assert not q.brand_exists(r.brand_id, active_only=True)
    assert q.brand_exists(r.brand_id, active_only=False)


# ── query service ────────────────────────────────────────────────────────────
def test_query_list_and_options(conn):
    _create(conn, "LAL", "Lala")
    _create(conn, "BIM", "Bimbo")
    q = ProductBrandQueryService(conn)
    names = [b["name"] for b in q.list_brands()]
    assert names == ["Bimbo", "Lala"]  # ordenado por nombre
    opts = q.options()
    assert {o["code"] for o in opts} == {"BIM", "LAL"}
    assert all(o["label"] and o["id"] for o in opts)


def test_query_options_excludes_inactive(conn):
    a = _create(conn, "BIM", "Bimbo")
    _create(conn, "LAL", "Lala")
    SetProductBrandActiveUseCase(conn, _MANAGE).execute(SetBrandActiveCommand(
        operation_id="op6", brand_id=a.brand_id, active=False, user_id="u1"))
    opts = ProductBrandQueryService(conn).options(active_only=True)
    assert {o["code"] for o in opts} == {"LAL"}
