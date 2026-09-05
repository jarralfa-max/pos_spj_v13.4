"""PROD-6 — productos internos: etapa (internal_stage) de punta a punta.

Antes de esta fase, `internal_stage` existía en el esquema y en la entidad
`Product` (coerción, invariante internal_only) pero NUNCA se escribía: ni
`CreateProductMasterCommand` lo aceptaba, ni `ProductMasterRepository.create/
update` lo incluían en su SQL — todo producto real nacía y quedaba para
siempre en `NONE`. `internal_product_policy.is_transformation()` tenía tests
unitarios pero cero llamadores reales. Estos tests prueban la cadena completa:
alta con etapa, preservación en edición (P0-01: editar no cambia etapa,
igual que no cambia lifecycle_status) y la transición vigilada por
`SetInternalStageUseCase`.
"""

from __future__ import annotations

import sqlite3

import pytest

from backend.application.products.authorization.policy import ProductsAuthorizationPolicy
from backend.application.products.commands.product_internal_stage_commands import (
    SetInternalStageCommand,
)
from backend.application.products.commands.product_master_commands import (
    CreateProductMasterCommand,
    UpdateProductMasterCommand,
)
from backend.application.products.permissions import ProductPermissions
from backend.application.products.use_cases.product_internal_stage_use_cases import (
    SetInternalStageUseCase,
)
from backend.application.products.use_cases.product_master_use_cases import (
    CreateProductMasterUseCase,
    UpdateProductMasterUseCase,
)
from backend.infrastructure.db.schema.products_schema import create_products_schema

_P = ProductPermissions


class _Checker:
    def __init__(self, granted):
        self._granted = set(granted)

    def has_permission(self, user_id, code):
        return code in self._granted


_ALL = ProductsAuthorizationPolicy(_Checker({
    _P.CREATE, _P.EDIT, _P.OVERRIDE_CODE, _P.INTERNAL_EDIT}))
_UNIT = "unit-kg"


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


def _create(conn, **kw):
    base = dict(operation_id="op", code="A-1", name="Masa cárnica", user_id="u1",
                product_type="RAW_MATERIAL", base_unit_id=_UNIT, category_id="cat1",
                sellable=False, internal_only=True)
    base.update(kw)
    return CreateProductMasterUseCase(conn, _ALL).execute(
        CreateProductMasterCommand(**base))


class TestInternalStageOnMaster:
    def test_create_with_wip_stage(self, conn):
        r = _create(conn, internal_stage="WORK_IN_PROGRESS")
        assert r.success
        row = conn.execute("SELECT internal_stage, internal_only FROM products "
                           "WHERE id=?", (r.product_id,)).fetchone()
        assert row["internal_stage"] == "WORK_IN_PROGRESS" and row["internal_only"] == 1

    def test_default_stage_is_none(self, conn):
        r = _create(conn, sellable=True, internal_only=False)
        row = conn.execute("SELECT internal_stage FROM products WHERE id=?",
                           (r.product_id,)).fetchone()
        assert row["internal_stage"] == "NONE"

    def test_update_preserves_stage(self, conn):
        r = _create(conn, internal_stage="WORK_IN_PROGRESS")
        UpdateProductMasterUseCase(conn, _ALL).execute(UpdateProductMasterCommand(
            operation_id="op2", product_id=r.product_id, code="A-1",
            name="Masa cárnica (renombrada)", product_type="RAW_MATERIAL",
            base_unit_id=_UNIT, category_id="cat1", user_id="u1",
            sellable=False, internal_only=True))
        row = conn.execute("SELECT internal_stage, name FROM products WHERE id=?",
                           (r.product_id,)).fetchone()
        # la edición renombra, pero NO resetea la etapa a NONE (P0-01 extendido)
        assert row["internal_stage"] == "WORK_IN_PROGRESS"
        assert row["name"] == "Masa cárnica (renombrada)"


class TestSetInternalStageUseCase:
    def test_non_transformation_change_allowed(self, conn):
        r = _create(conn, sellable=False, internal_only=False,
                    internal_stage="NONE")
        result = SetInternalStageUseCase(conn, _ALL).execute(SetInternalStageCommand(
            operation_id="op2", product_id=r.product_id, stage="INTERNAL_ONLY",
            user_id="u1"))
        assert result.success
        row = conn.execute("SELECT internal_stage, internal_only FROM products "
                           "WHERE id=?", (r.product_id,)).fetchone()
        assert row["internal_stage"] == "INTERNAL_ONLY" and row["internal_only"] == 1

    def test_real_transformation_rejected(self, conn):
        r = _create(conn, internal_stage="WORK_IN_PROGRESS")
        result = SetInternalStageUseCase(conn, _ALL).execute(SetInternalStageCommand(
            operation_id="op2", product_id=r.product_id, stage="SEMI_FINISHED",
            user_id="u1"))
        assert not result.success
        assert "transformación" in result.message.lower()
        row = conn.execute("SELECT internal_stage FROM products WHERE id=?",
                           (r.product_id,)).fetchone()
        assert row["internal_stage"] == "WORK_IN_PROGRESS"  # sin cambios

    def test_sellable_product_cannot_move_to_internal_stage(self, conn):
        r = _create(conn, sellable=True, internal_only=False, internal_stage="NONE")
        result = SetInternalStageUseCase(conn, _ALL).execute(SetInternalStageCommand(
            operation_id="op2", product_id=r.product_id,
            stage="INTERNAL_ONLY", user_id="u1"))
        assert not result.success and "vendible" in result.message.lower()

    def test_requires_permission(self, conn):
        r = _create(conn, internal_stage="NONE")
        no_perm = ProductsAuthorizationPolicy(_Checker(set()))
        from backend.domain.products.exceptions import ProductPermissionDeniedError
        with pytest.raises(ProductPermissionDeniedError):
            SetInternalStageUseCase(conn, no_perm).execute(SetInternalStageCommand(
                operation_id="op2", product_id=r.product_id, stage="INTERNAL_ONLY"))

    def test_stage_change_writes_audit_entry(self, conn):
        r = _create(conn, sellable=False, internal_only=False, internal_stage="NONE")
        SetInternalStageUseCase(conn, _ALL).execute(SetInternalStageCommand(
            operation_id="op2", product_id=r.product_id, stage="INTERNAL_ONLY",
            user_id="u1"))
        row = conn.execute(
            "SELECT action FROM product_audit_log WHERE entity_id=? "
            "AND action='PRODUCT_INTERNAL_STAGE_CHANGED'", (r.product_id,)).fetchone()
        assert row is not None
