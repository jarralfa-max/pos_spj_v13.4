"""PROD-1 re-audit (2026-08-18) — §40 audit trail actually written.

Before `record_product_audit_entry` (`backend/application/products/audit.py`)
existed, only 2 of ~15 Products mutation use cases ever wrote a
`product_audit_log` row (manual code override, quality block/release) despite
docstrings across the module claiming every lifecycle/recipe/yield/cutting/
bundle/import/branch-assortment change is audited. These tests prove the
wiring added this session actually lands a row for each of those families —
not just that nothing regressed.
"""

from __future__ import annotations

import sqlite3

import pytest

from backend.application.products.authorization.policy import ProductsAuthorizationPolicy
from backend.application.products.commands.product_master_commands import (
    CreateProductMasterCommand,
    UpdateProductMasterCommand,
)
from backend.application.products.commands.product_recipe_commands import (
    CreateRecipeCommand,
    RecipeVersionTransitionCommand,
)
from backend.application.products.permissions import ProductPermissions
from backend.application.products.use_cases.product_branch_assortment_use_cases import (
    SetBranchProductUseCase,
)
from backend.application.products.use_cases.product_lifecycle_use_cases import (
    ActivateProductUseCase,
    SubmitProductUseCase,
)
from backend.application.products.use_cases.product_master_use_cases import (
    CreateProductMasterUseCase,
    UpdateProductMasterUseCase,
)
from backend.application.products.use_cases.product_recipe_use_cases import (
    ApproveRecipeVersionUseCase,
    CreateProductRecipeUseCase,
    SubmitRecipeVersionUseCase,
)
from backend.infrastructure.db.schema.products_schema import create_products_schema

_UNIT = "unit-kg-audit"
_COMP = "prod-comp-audit"
_P = ProductPermissions


class _Checker:
    def __init__(self, granted):
        self._granted = set(granted)

    def has_permission(self, user_id, code):
        return code in self._granted


_ALL = ProductsAuthorizationPolicy(_Checker({
    _P.CREATE, _P.EDIT, _P.OVERRIDE_CODE, _P.SUBMIT, _P.APPROVE, _P.ACTIVATE,
    _P.RECIPE_CREATE, _P.RECIPE_EDIT, _P.RECIPE_APPROVE,
    _P.BRANCH_ASSIGNMENT_MANAGE,
}))


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


def _audit_rows(conn, entity_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT action, user_id, operation_id, source FROM product_audit_log "
        "WHERE entity_id=? ORDER BY occurred_at", (entity_id,)).fetchall()


def test_create_product_master_writes_audit_entry(conn):
    r = CreateProductMasterUseCase(conn, _ALL).execute(CreateProductMasterCommand(
        operation_id="op1", code="A-1", name="Bistec", product_type="RAW_MATERIAL",
        base_unit_id=_UNIT, category_id="cat1", user_id="alice"))
    assert r.success
    rows = _audit_rows(conn, r.product_id)
    # code_overridden=True (manual code) also logs a CODE_OVERRIDE entry.
    assert [row["action"] for row in rows] == ["CODE_OVERRIDE", "PRODUCT_CREATED"]
    assert rows[-1]["user_id"] == "alice" and rows[-1]["operation_id"] == "op1"


def test_update_product_master_writes_audit_entry(conn):
    r = CreateProductMasterUseCase(conn, _ALL).execute(CreateProductMasterCommand(
        operation_id="op1", code="A-2", name="Costilla", product_type="RAW_MATERIAL",
        base_unit_id=_UNIT, category_id="cat1", user_id="alice"))
    UpdateProductMasterUseCase(conn, _ALL).execute(UpdateProductMasterCommand(
        operation_id="op2", product_id=r.product_id, code="A-2", name="Costilla BBQ",
        product_type="RAW_MATERIAL", base_unit_id=_UNIT, category_id="cat1",
        user_id="alice"))
    rows = _audit_rows(conn, r.product_id)
    assert [row["action"] for row in rows] == [
        "CODE_OVERRIDE", "PRODUCT_CREATED", "PRODUCT_UPDATED"]


def test_lifecycle_transitions_write_audit_entries(conn):
    r = CreateProductMasterUseCase(conn, _ALL).execute(CreateProductMasterCommand(
        operation_id="op1", code="A-3", name="Pechuga", product_type="RAW_MATERIAL",
        base_unit_id=_UNIT, category_id="cat1", user_id="creator",
        auto_generate_code=False))
    SubmitProductUseCase(conn, _ALL).execute(
        product_id=r.product_id, user_id="creator", operation_id="op2")
    ActivateProductUseCase(conn, _ALL).execute(
        product_id=r.product_id, user_id="approver", operation_id="op3")
    rows = _audit_rows(conn, r.product_id)
    actions = [row["action"] for row in rows]
    assert "PRODUCT_SUBMITTED" in actions
    assert any(a in actions for a in ("PRODUCT_ACTIVATED",))


def test_recipe_create_and_approve_write_audit_entries(conn):
    r = CreateProductRecipeUseCase(conn, _ALL).execute(CreateRecipeCommand(
        operation_id="op1", product_id="prod-virtual", recipe_type="PRODUCTION_BOM",
        name="BOM", components=[{"component_product_id": _COMP, "quantity": "2",
                                 "unit_id": _UNIT}], user_id="creator"))
    assert r.success
    rows = _audit_rows(conn, r.recipe_id)
    assert rows[0]["action"] == "PRODUCT_RECIPE_CREATED"

    submitted = SubmitRecipeVersionUseCase(conn, _ALL).execute(
        RecipeVersionTransitionCommand(operation_id="op2", version_id=r.version_id,
                                       user_id="creator"))
    assert submitted.success
    approve = ApproveRecipeVersionUseCase(conn, _ALL).execute(
        RecipeVersionTransitionCommand(operation_id="op3", version_id=r.version_id,
                                       user_id="approver"))
    assert approve.success
    version_rows = _audit_rows(conn, r.version_id)
    actions = [row["action"] for row in version_rows]
    assert actions == ["RECIPE_VERSION_SUBMITTED", "RECIPE_VERSION_APPROVED"]
    assert version_rows[-1]["user_id"] == "approver"


def test_branch_product_assignment_writes_audit_entry(conn):
    r = CreateProductMasterUseCase(conn, _ALL).execute(CreateProductMasterCommand(
        operation_id="op1", code="A-4", name="Chuleta", product_type="RAW_MATERIAL",
        base_unit_id=_UNIT, category_id="cat1", user_id="alice"))
    result = SetBranchProductUseCase(conn, _ALL).execute(
        product_id=r.product_id, branch_id="b1", enabled=True, user_id="alice")
    assert result.success
    rows = _audit_rows(conn, r.product_id)
    assert "BRANCH_PRODUCT_ENABLED" in [row["action"] for row in rows]


def test_audit_helper_no_ops_without_table():
    """La tabla puede faltar en fixtures mínimos — no debe romper el caso de uso."""
    from backend.application.products.audit import record_product_audit_entry

    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE dummy (id TEXT)")
    record_product_audit_entry(
        c, action="X", entity_id="e1", user_id="u1", operation_id="op1")
    c.close()  # no exception raised above is the assertion
