"""P1 — galería de imágenes: agregar/principal/eliminar (una principal) + query."""

import sqlite3

import pytest

from backend.application.products.authorization.policy import ProductsAuthorizationPolicy
from backend.application.products.commands.product_image_commands import (
    AddProductImageCommand,
    RemoveProductImageCommand,
    SetPrimaryImageCommand,
)
from backend.application.products.permissions import ProductPermissions
from backend.application.products.queries.product_image_query_service import (
    ProductImageQueryService,
)
from backend.application.products.use_cases.product_image_use_cases import (
    AddProductImageUseCase,
    RemoveProductImageUseCase,
    SetPrimaryImageUseCase,
)
from backend.domain.products.entities.product_image import ProductImage
from backend.domain.products.exceptions import (
    InvalidProductImageError,
    ProductPermissionDeniedError,
)
from backend.infrastructure.db.schema.products_schema import create_products_schema

_PID = "prod-1"


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


_MANAGE = ProductsAuthorizationPolicy(_Checker({ProductPermissions.IMAGES_MANAGE}))


def _add(conn, uri, make_primary=False, auth=None):
    return AddProductImageUseCase(conn, auth or _MANAGE).execute(
        AddProductImageCommand(operation_id="op", product_id=_PID, uri=uri,
                               make_primary=make_primary, user_id="u1"))


def test_entity_requires_product_and_uri():
    with pytest.raises(InvalidProductImageError):
        ProductImage(product_id="", uri="x")
    with pytest.raises(InvalidProductImageError):
        ProductImage(product_id="p", uri="")


def test_first_image_becomes_primary(conn):
    r = _add(conn, "/img/a.png")
    assert r.success
    row = conn.execute("SELECT is_primary FROM product_images WHERE id=?",
                       (r.image_id,)).fetchone()
    assert row["is_primary"] == 1


def test_second_image_not_primary_by_default(conn):
    _add(conn, "/img/a.png")
    second = _add(conn, "/img/b.png")
    assert conn.execute("SELECT is_primary FROM product_images WHERE id=?",
                        (second.image_id,)).fetchone()["is_primary"] == 0


def test_only_one_primary_after_set(conn):
    a = _add(conn, "/img/a.png")
    b = _add(conn, "/img/b.png")
    SetPrimaryImageUseCase(conn, _MANAGE).execute(SetPrimaryImageCommand(
        operation_id="op2", image_id=b.image_id, user_id="u1"))
    primaries = conn.execute(
        "SELECT id FROM product_images WHERE product_id=? AND is_primary=1",
        (_PID,)).fetchall()
    assert len(primaries) == 1 and primaries[0]["id"] == b.image_id
    _ = a


def test_remove_primary_promotes_another(conn):
    a = _add(conn, "/img/a.png")  # principal
    b = _add(conn, "/img/b.png")
    RemoveProductImageUseCase(conn, _MANAGE).execute(RemoveProductImageCommand(
        operation_id="op3", image_id=a.image_id, user_id="u1"))
    remaining = conn.execute(
        "SELECT id, is_primary FROM product_images WHERE product_id=?",
        (_PID,)).fetchall()
    assert len(remaining) == 1 and remaining[0]["id"] == b.image_id
    assert remaining[0]["is_primary"] == 1


def test_add_requires_permission(conn):
    auth = ProductsAuthorizationPolicy(_Checker(set()))
    with pytest.raises(ProductPermissionDeniedError):
        _add(conn, "/img/a.png", auth=auth)


def test_add_emits_event(conn):
    r = _add(conn, "/img/a.png")
    row = conn.execute("SELECT event_name FROM product_outbox WHERE entity_id=?",
                       (r.image_id,)).fetchone()
    assert row["event_name"] == "PRODUCT_IMAGE_ADDED"


def test_query_lists_primary_first(conn):
    _add(conn, "/img/a.png")
    b = _add(conn, "/img/b.png", make_primary=True)
    q = ProductImageQueryService(conn)
    images = q.list_images(_PID)
    assert images[0]["id"] == b.image_id and images[0]["is_primary"]
    assert q.primary_image(_PID)["id"] == b.image_id
