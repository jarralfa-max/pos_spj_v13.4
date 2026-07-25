"""P1-01 — política pura de jerarquía de categorías (rutas, profundidad, ciclos)."""

import pytest

from backend.domain.products.entities.product_category import (
    ProductCategory,
    normalize_name,
)
from backend.domain.products.exceptions import (
    CategoryCycleDetectedError,
    CategoryDepthExceededError,
    InvalidCategoryError,
)
from backend.domain.products.policies.product_category_hierarchy_policy import (
    MAX_DEPTH,
    child_depth,
    child_path,
    ensure_acyclic_reparent,
    ensure_within_depth,
    is_descendant_of,
)


def test_entity_requires_code_and_name():
    with pytest.raises(InvalidCategoryError):
        ProductCategory(code="", name="Carnes")
    with pytest.raises(InvalidCategoryError):
        ProductCategory(code="CARN", name="")


def test_entity_uppercases_code_and_normalizes_name():
    c = ProductCategory(code="carn", name="  Carnes  Rojas ")
    assert c.code == "CARN" and c.name == "Carnes  Rojas"
    assert c.name_normalized == "carnes rojas"
    assert normalize_name("  A  b ") == "a b"


def test_child_path_and_depth():
    assert child_path(None, "root1") == "/root1/"
    assert child_path("/root1/", "child1") == "/root1/child1/"
    assert child_depth(None) == 0
    assert child_depth(2) == 3


def test_is_descendant_of():
    assert is_descendant_of("/a/b/c/", "b")
    assert is_descendant_of("/a/b/c/", "a")
    assert not is_descendant_of("/a/b/c/", "z")


def test_ensure_within_depth():
    ensure_within_depth(MAX_DEPTH)  # borde válido
    with pytest.raises(CategoryDepthExceededError):
        ensure_within_depth(MAX_DEPTH + 1)


def test_reparent_rejects_self_parent():
    with pytest.raises(CategoryCycleDetectedError):
        ensure_acyclic_reparent(category_id="x", category_path="/x/",
                                new_parent_id="x", new_parent_path="/x/")


def test_reparent_rejects_descendant_parent():
    # Mover 'a' bajo su descendiente 'b' (path /a/b/) → ciclo.
    with pytest.raises(CategoryCycleDetectedError):
        ensure_acyclic_reparent(category_id="a", category_path="/a/",
                                new_parent_id="b", new_parent_path="/a/b/")


def test_reparent_to_root_is_allowed():
    ensure_acyclic_reparent(category_id="a", category_path="/x/a/",
                            new_parent_id=None, new_parent_path=None)
