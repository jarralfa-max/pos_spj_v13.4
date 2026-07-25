"""P1-03 — generación de variantes: producto cartesiano + herencia + idempotencia."""

import sqlite3

import pytest

from backend.application.products.authorization.policy import ProductsAuthorizationPolicy
from backend.application.products.commands.product_attribute_commands import (
    AddAttributeOptionCommand,
    CreateAttributeCommand,
)
from backend.application.products.commands.product_master_commands import (
    CreateProductMasterCommand,
)
from backend.application.products.commands.product_variant_commands import (
    GenerateVariantsCommand,
)
from backend.application.products.permissions import ProductPermissions
from backend.application.products.queries.product_variant_query_service import (
    ProductVariantQueryService,
)
from backend.application.products.use_cases.product_attribute_use_cases import (
    AddAttributeOptionUseCase,
    CreateProductAttributeUseCase,
)
from backend.application.products.use_cases.product_master_use_cases import (
    CreateProductMasterUseCase,
)
from backend.application.products.use_cases.product_variant_use_cases import (
    GenerateProductVariantsUseCase,
)
from backend.domain.products.exceptions import (
    InvalidVariantError,
    ProductPermissionDeniedError,
)
from backend.domain.products.policies.product_variant_policy import (
    cartesian_combinations,
)
from backend.infrastructure.db.schema.products_schema import create_products_schema

_UNIT_ID = "unit-kg-0001"


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_products_schema(c)
    c.execute("INSERT INTO units_of_measure (id, code, name, dimension, active) "
              "VALUES (?, 'KG', 'Kilogramo', 'WEIGHT', 1)", (_UNIT_ID,))
    c.execute("INSERT INTO product_code_generation_rules "
              "(id, scope_type, scope_value, prefix, padding, separator, active) "
              "VALUES ('r0','DEFAULT','','PRD',6,'-',1)")
    c.commit()
    yield c
    c.close()


_ALL = ProductsAuthorizationPolicy(None)  # permisiva (sin checker) para setup


def _parent(conn):
    r = CreateProductMasterUseCase(conn).execute(CreateProductMasterCommand(
        operation_id="op", code="PLAY-1", name="Playera", product_type="RESALE_PRODUCT",
        base_unit_id=_UNIT_ID, user_id="u1", category_id="cat-1"))
    return r.product_id


def _attr_with_options(conn, code, name, options):
    a = CreateProductAttributeUseCase(conn).execute(CreateAttributeCommand(
        operation_id="opa", code=code, name=name, user_id="u1")).entity_id
    ids = []
    for oc, ol in options:
        ids.append(AddAttributeOptionUseCase(conn).execute(AddAttributeOptionCommand(
            operation_id="opo", attribute_id=a, code=oc, label=ol, user_id="u1")
        ).entity_id)
    return a, ids


# ── política pura ────────────────────────────────────────────────────────────
def test_cartesian_product():
    combos = cartesian_combinations([("c", ["r", "a"]), ("t", ["s", "m"])])
    assert len(combos) == 4
    assert (("c", "r"), ("t", "s")) in combos


def test_cartesian_rejects_empty_axes():
    with pytest.raises(InvalidVariantError):
        cartesian_combinations([])
    with pytest.raises(InvalidVariantError):
        cartesian_combinations([("c", [])])


# ── generación ───────────────────────────────────────────────────────────────
def _generate(conn, parent_id, axes, auth=None):
    return GenerateProductVariantsUseCase(conn, auth).execute(GenerateVariantsCommand(
        operation_id="opg", parent_product_id=parent_id, axes=axes, user_id="u1"))


def test_generates_cartesian_variants(conn):
    parent = _parent(conn)
    color, colors = _attr_with_options(conn, "COL", "Color",
                                       [("ROJ", "Rojo"), ("AZU", "Azul")])
    talla, tallas = _attr_with_options(conn, "TAL", "Talla",
                                       [("S", "Chica"), ("M", "Mediana")])
    r = _generate(conn, parent, {color: colors, talla: tallas})
    assert r.success and r.generated == 4 and r.skipped == 0
    kids = conn.execute("SELECT COUNT(*) AS n FROM products WHERE parent_product_id=?",
                        (parent,)).fetchone()["n"]
    assert kids == 4


def test_variants_inherit_parent_config_and_are_draft(conn):
    parent = _parent(conn)
    color, colors = _attr_with_options(conn, "COL", "Color", [("ROJ", "Rojo")])
    _generate(conn, parent, {color: colors})
    row = conn.execute(
        "SELECT product_type, base_unit_id, category_id, lifecycle_status, name "
        "FROM products WHERE parent_product_id=?", (parent,)).fetchone()
    assert row["product_type"] == "RESALE_PRODUCT" and row["base_unit_id"] == _UNIT_ID
    assert row["category_id"] == "cat-1" and row["lifecycle_status"] == "DRAFT"
    assert row["name"] == "Playera - Rojo"


def test_generation_is_idempotent_on_rerun(conn):
    parent = _parent(conn)
    color, colors = _attr_with_options(conn, "COL", "Color",
                                       [("ROJ", "Rojo"), ("AZU", "Azul")])
    first = _generate(conn, parent, {color: colors})
    assert first.generated == 2
    second = _generate(conn, parent, {color: colors})
    assert second.generated == 0 and second.skipped == 2
    total = conn.execute("SELECT COUNT(*) AS n FROM products WHERE parent_product_id=?",
                         (parent,)).fetchone()["n"]
    assert total == 2  # no se duplican


def test_records_assignments(conn):
    parent = _parent(conn)
    color, colors = _attr_with_options(conn, "COL", "Color", [("ROJ", "Rojo")])
    _generate(conn, parent, {color: colors})
    n = conn.execute("SELECT COUNT(*) AS n FROM product_variant_assignments").fetchone()
    assert n["n"] == 1


def test_generation_requires_permission(conn):
    parent = _parent(conn)
    color, colors = _attr_with_options(conn, "COL", "Color", [("ROJ", "Rojo")])

    class _Checker:
        def has_permission(self, user_id, code):
            return False

    with pytest.raises(ProductPermissionDeniedError):
        _generate(conn, parent, {color: colors},
                  auth=ProductsAuthorizationPolicy(_Checker()))


def test_unknown_parent(conn):
    color, colors = _attr_with_options(conn, "COL", "Color", [("ROJ", "Rojo")])
    r = _generate(conn, "nope", {color: colors})
    assert not r.success and "padre no existe" in r.message


# ── query service ────────────────────────────────────────────────────────────
def test_query_lists_variants_with_attribute_values(conn):
    parent = _parent(conn)
    color, colors = _attr_with_options(conn, "COL", "Color", [("ROJ", "Rojo")])
    _generate(conn, parent, {color: colors})
    q = ProductVariantQueryService(conn)
    assert q.variant_count(parent) == 1
    variants = q.list_variants(parent)
    assert variants[0]["attributes"] == [{"attribute": "Color", "value": "Rojo"}]
