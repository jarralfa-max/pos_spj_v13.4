"""P1-01 — árbol de categorías: alta/edición/movimiento/activación + query service."""

import json
import sqlite3

import pytest

from backend.application.products.authorization.policy import ProductsAuthorizationPolicy
from backend.application.products.commands.product_category_commands import (
    CreateCategoryCommand,
    MoveCategoryCommand,
    SetCategoryActiveCommand,
    UpdateCategoryCommand,
)
from backend.application.products.permissions import ProductPermissions
from backend.application.products.queries.product_category_query_service import (
    ProductCategoryQueryService,
)
from backend.application.products.use_cases.product_category_use_cases import (
    CreateProductCategoryUseCase,
    MoveProductCategoryUseCase,
    SetProductCategoryActiveUseCase,
    UpdateProductCategoryUseCase,
)
from backend.domain.products.exceptions import ProductPermissionDeniedError
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


_MANAGE = ProductsAuthorizationPolicy(
    _Checker({ProductPermissions.CATEGORIES_MANAGE}))


def _create(conn, code, name, parent_id=None, auth=None):
    return CreateProductCategoryUseCase(conn, auth or _MANAGE).execute(
        CreateCategoryCommand(operation_id="op", code=code, name=name,
                              parent_id=parent_id, user_id="u1"))


def test_create_root_category(conn):
    r = _create(conn, "CARN", "Carnes")
    assert r.success and r.category_id
    row = conn.execute("SELECT * FROM product_categories WHERE id=?",
                       (r.category_id,)).fetchone()
    assert row["code"] == "CARN" and row["parent_id"] is None
    assert row["depth"] == 0 and row["path"] == f"/{r.category_id}/"


def test_create_child_derives_path_and_depth(conn):
    root = _create(conn, "CARN", "Carnes")
    child = _create(conn, "RES", "Res", parent_id=root.category_id)
    row = conn.execute("SELECT * FROM product_categories WHERE id=?",
                       (child.category_id,)).fetchone()
    assert row["depth"] == 1
    assert row["path"] == f"/{root.category_id}/{child.category_id}/"


def test_create_rejects_duplicate_code(conn):
    _create(conn, "CARN", "Carnes")
    r = _create(conn, "CARN", "Otra")
    assert not r.success and "ya existe" in r.message


def test_create_rejects_unknown_parent(conn):
    r = _create(conn, "RES", "Res", parent_id="nope")
    assert not r.success and "padre no existe" in r.message


def test_create_requires_manage_permission(conn):
    auth = ProductsAuthorizationPolicy(_Checker(set()))
    with pytest.raises(ProductPermissionDeniedError):
        _create(conn, "CARN", "Carnes", auth=auth)


def test_create_emits_outbox_event(conn):
    r = _create(conn, "CARN", "Carnes")
    row = conn.execute("SELECT event_name, payload FROM product_outbox WHERE entity_id=?",
                       (r.category_id,)).fetchone()
    assert row["event_name"] == "PRODUCT_CATEGORY_CREATED"
    assert json.loads(row["payload"])["code"] == "CARN"


def test_depth_limit_enforced(conn):
    from backend.domain.products.policies.product_category_hierarchy_policy import MAX_DEPTH
    parent_id = None
    last = None
    for i in range(MAX_DEPTH + 1):  # 0..MAX_DEPTH = MAX_DEPTH+1 niveles OK
        last = _create(conn, f"C{i}", f"N{i}", parent_id=parent_id)
        assert last.success
        parent_id = last.category_id
    # El siguiente nivel excede MAX_DEPTH.
    overflow = _create(conn, "CX", "Overflow", parent_id=parent_id)
    assert not overflow.success and "profundidad" in overflow.message.lower()


def test_update_changes_code_and_name(conn):
    root = _create(conn, "CARN", "Carnes")
    r = UpdateProductCategoryUseCase(conn, _MANAGE).execute(UpdateCategoryCommand(
        operation_id="op2", category_id=root.category_id, code="CARNE",
        name="Carnes Rojas", user_id="u1"))
    assert r.success
    row = conn.execute("SELECT code, name, name_normalized FROM product_categories "
                       "WHERE id=?", (root.category_id,)).fetchone()
    assert row["code"] == "CARNE" and row["name"] == "Carnes Rojas"
    assert row["name_normalized"] == "carnes rojas"


def test_move_reparents_and_rewrites_subtree(conn):
    a = _create(conn, "A", "A")
    b = _create(conn, "B", "B")
    a_child = _create(conn, "AC", "A-Child", parent_id=a.category_id)
    # Mover A (con su hijo) bajo B.
    r = MoveProductCategoryUseCase(conn, _MANAGE).execute(MoveCategoryCommand(
        operation_id="op3", category_id=a.category_id, new_parent_id=b.category_id,
        user_id="u1"))
    assert r.success
    a_row = conn.execute("SELECT parent_id, depth, path FROM product_categories "
                         "WHERE id=?", (a.category_id,)).fetchone()
    assert a_row["parent_id"] == b.category_id and a_row["depth"] == 1
    assert a_row["path"] == f"/{b.category_id}/{a.category_id}/"
    # El descendiente se reescribió: depth 2 y path bajo B.
    child_row = conn.execute("SELECT depth, path FROM product_categories WHERE id=?",
                             (a_child.category_id,)).fetchone()
    assert child_row["depth"] == 2
    assert child_row["path"] == \
        f"/{b.category_id}/{a.category_id}/{a_child.category_id}/"


def test_move_rejects_cycle(conn):
    a = _create(conn, "A", "A")
    a_child = _create(conn, "AC", "A-Child", parent_id=a.category_id)
    # Mover A bajo su propio hijo → ciclo.
    r = MoveProductCategoryUseCase(conn, _MANAGE).execute(MoveCategoryCommand(
        operation_id="op4", category_id=a.category_id,
        new_parent_id=a_child.category_id, user_id="u1"))
    assert not r.success and "subárbol" in r.message.lower()


def test_deactivate_blocked_by_active_children(conn):
    root = _create(conn, "CARN", "Carnes")
    _create(conn, "RES", "Res", parent_id=root.category_id)
    r = SetProductCategoryActiveUseCase(conn, _MANAGE).execute(SetCategoryActiveCommand(
        operation_id="op5", category_id=root.category_id, active=False, user_id="u1"))
    assert not r.success and "subcategorías activas" in r.message


def test_deactivate_leaf_succeeds(conn):
    root = _create(conn, "CARN", "Carnes")
    leaf = _create(conn, "RES", "Res", parent_id=root.category_id)
    r = SetProductCategoryActiveUseCase(conn, _MANAGE).execute(SetCategoryActiveCommand(
        operation_id="op6", category_id=leaf.category_id, active=False, user_id="u1"))
    assert r.success
    assert conn.execute("SELECT active FROM product_categories WHERE id=?",
                        (leaf.category_id,)).fetchone()["active"] == 0


# ── query service ────────────────────────────────────────────────────────────
def test_query_tree_nests_children(conn):
    root = _create(conn, "CARN", "Carnes")
    _create(conn, "RES", "Res", parent_id=root.category_id)
    _create(conn, "CER", "Cerdo", parent_id=root.category_id)
    tree = ProductCategoryQueryService(conn).tree()
    assert len(tree) == 1 and tree[0]["code"] == "CARN"
    assert {c["code"] for c in tree[0]["children"]} == {"RES", "CER"}


def test_query_flat_options_indent_by_depth(conn):
    root = _create(conn, "CARN", "Carnes")
    _create(conn, "RES", "Res", parent_id=root.category_id)
    opts = ProductCategoryQueryService(conn).flat_options()
    labels = {o["code"]: o["label"] for o in opts}
    assert labels["CARN"] == "Carnes"
    assert labels["RES"].startswith("   ") and "Res" in labels["RES"]
    assert {o["id"] for o in opts} == {root.category_id} | {
        o["id"] for o in opts if o["code"] == "RES"}


def test_query_breadcrumb(conn):
    root = _create(conn, "CARN", "Carnes")
    child = _create(conn, "RES", "Res", parent_id=root.category_id)
    crumb = ProductCategoryQueryService(conn).breadcrumb(child.category_id)
    assert [c["name"] for c in crumb] == ["Carnes", "Res"]


def test_query_category_exists_respects_active(conn):
    root = _create(conn, "CARN", "Carnes")
    q = ProductCategoryQueryService(conn)
    assert q.category_exists(root.category_id)
    SetProductCategoryActiveUseCase(conn, _MANAGE).execute(SetCategoryActiveCommand(
        operation_id="op7", category_id=root.category_id, active=False, user_id="u1"))
    assert not q.category_exists(root.category_id, active_only=True)
    assert q.category_exists(root.category_id, active_only=False)
