"""P1-03 — atributos configurables + opciones: use cases + query service."""

import json
import sqlite3

import pytest

from backend.application.products.authorization.policy import ProductsAuthorizationPolicy
from backend.application.products.commands.product_attribute_commands import (
    AddAttributeOptionCommand,
    CreateAttributeCommand,
    SetAttributeActiveCommand,
    UpdateAttributeCommand,
    UpdateAttributeOptionCommand,
)
from backend.application.products.permissions import ProductPermissions
from backend.application.products.queries.product_attribute_query_service import (
    ProductAttributeQueryService,
)
from backend.application.products.use_cases.product_attribute_use_cases import (
    AddAttributeOptionUseCase,
    CreateProductAttributeUseCase,
    SetProductAttributeActiveUseCase,
    UpdateAttributeOptionUseCase,
    UpdateProductAttributeUseCase,
)
from backend.domain.products.entities.product_attribute import (
    AttributeDataType,
    ProductAttribute,
)
from backend.domain.products.exceptions import (
    InvalidAttributeError,
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


_MANAGE = ProductsAuthorizationPolicy(_Checker({ProductPermissions.ATTRIBUTES_MANAGE}))


def _attr(conn, code, name, data_type="LIST", auth=None):
    return CreateProductAttributeUseCase(conn, auth or _MANAGE).execute(
        CreateAttributeCommand(operation_id="op", code=code, name=name,
                               data_type=data_type, user_id="u1"))


def _option(conn, attribute_id, code, label, **kw):
    return AddAttributeOptionUseCase(conn, _MANAGE).execute(AddAttributeOptionCommand(
        operation_id="opo", attribute_id=attribute_id, code=code, label=label,
        user_id="u1", **kw))


# ── entidad ──────────────────────────────────────────────────────────────────
def test_entity_validates_type():
    with pytest.raises(InvalidAttributeError):
        ProductAttribute(code="X", name="X", data_type="BOGUS")
    a = ProductAttribute(code="col", name="Color", data_type="LIST")
    assert a.code == "COL" and a.data_type is AttributeDataType.LIST and a.is_list


# ── atributos ────────────────────────────────────────────────────────────────
def test_create_attribute(conn):
    r = _attr(conn, "COL", "Color")
    assert r.success and r.entity_id
    row = conn.execute("SELECT * FROM product_attributes WHERE id=?",
                       (r.entity_id,)).fetchone()
    assert row["code"] == "COL" and row["data_type"] == "LIST" and row["active"] == 1


def test_create_rejects_duplicate_code(conn):
    _attr(conn, "COL", "Color")
    r = _attr(conn, "COL", "Otro")
    assert not r.success and "ya existe" in r.message


def test_create_requires_manage(conn):
    auth = ProductsAuthorizationPolicy(_Checker(set()))
    with pytest.raises(ProductPermissionDeniedError):
        _attr(conn, "COL", "Color", auth=auth)


def test_create_emits_event(conn):
    r = _attr(conn, "COL", "Color")
    row = conn.execute("SELECT event_name, payload FROM product_outbox WHERE entity_id=?",
                       (r.entity_id,)).fetchone()
    assert row["event_name"] == "PRODUCT_ATTRIBUTE_CREATED"
    assert json.loads(row["payload"])["data_type"] == "LIST"


def test_update_attribute_name(conn):
    a = _attr(conn, "COL", "Color")
    r = UpdateProductAttributeUseCase(conn, _MANAGE).execute(UpdateAttributeCommand(
        operation_id="op2", attribute_id=a.entity_id, code="COLOR", name="Color base",
        user_id="u1"))
    assert r.success
    row = conn.execute("SELECT code, name FROM product_attributes WHERE id=?",
                       (a.entity_id,)).fetchone()
    assert row["code"] == "COLOR" and row["name"] == "Color base"


def test_deactivate_attribute(conn):
    a = _attr(conn, "COL", "Color")
    r = SetProductAttributeActiveUseCase(conn, _MANAGE).execute(
        SetAttributeActiveCommand(operation_id="op3", attribute_id=a.entity_id,
                                  active=False, user_id="u1"))
    assert r.success
    assert conn.execute("SELECT active FROM product_attributes WHERE id=?",
                        (a.entity_id,)).fetchone()["active"] == 0


# ── opciones ─────────────────────────────────────────────────────────────────
def test_add_option_to_list_attribute(conn):
    a = _attr(conn, "COL", "Color")
    r = _option(conn, a.entity_id, "ROJ", "Rojo")
    assert r.success
    row = conn.execute("SELECT * FROM product_attribute_options WHERE id=?",
                       (r.entity_id,)).fetchone()
    assert row["code"] == "ROJ" and row["label"] == "Rojo"


def test_add_option_rejected_on_non_list(conn):
    a = _attr(conn, "PESO", "Peso", data_type="NUMBER")
    r = _option(conn, a.entity_id, "X", "X")
    assert not r.success and "lista" in r.message.lower()


def test_add_option_rejects_duplicate_code(conn):
    a = _attr(conn, "COL", "Color")
    _option(conn, a.entity_id, "ROJ", "Rojo")
    r = _option(conn, a.entity_id, "ROJ", "Rojo Oscuro")
    assert not r.success and "ya existe" in r.message


def test_update_option(conn):
    a = _attr(conn, "COL", "Color")
    o = _option(conn, a.entity_id, "ROJ", "Rojo")
    r = UpdateAttributeOptionUseCase(conn, _MANAGE).execute(UpdateAttributeOptionCommand(
        operation_id="opu", option_id=o.entity_id, code="ROJO", label="Rojo intenso",
        sort_order=2, active=True, user_id="u1"))
    assert r.success
    row = conn.execute("SELECT code, label, sort_order FROM product_attribute_options "
                       "WHERE id=?", (o.entity_id,)).fetchone()
    assert row["code"] == "ROJO" and row["label"] == "Rojo intenso"
    assert row["sort_order"] == 2


# ── query service ────────────────────────────────────────────────────────────
def test_query_attributes_with_options(conn):
    color = _attr(conn, "COL", "Color")
    _attr(conn, "PESO", "Peso", data_type="NUMBER")  # no LIST → excluido
    _option(conn, color.entity_id, "ROJ", "Rojo", sort_order=1)
    _option(conn, color.entity_id, "AZU", "Azul", sort_order=2)
    combos = ProductAttributeQueryService(conn).attributes_with_options()
    assert len(combos) == 1 and combos[0]["code"] == "COL"
    assert [o["code"] for o in combos[0]["options"]] == ["ROJ", "AZU"]
