"""P0-04 — generación configurable del código de producto.

Cubre la política pura (precedencia/formato), el repositorio de secuencias
(peek no consume, reserve sí), la vista previa, y el alta con código automático o
manual (override con permiso + auditoría).
"""

import json
import sqlite3

import pytest

from backend.application.products.authorization.policy import ProductsAuthorizationPolicy
from backend.application.products.commands.product_master_commands import (
    CreateProductMasterCommand,
)
from backend.application.products.permissions import ProductPermissions
from backend.application.products.queries.product_code_query_service import (
    PreviewProductCodeQueryService,
    reserve_next_code,
)
from backend.application.products.use_cases.product_master_use_cases import (
    CreateProductMasterUseCase,
)
from backend.domain.products.exceptions import ProductPermissionDeniedError
from backend.domain.products.policies.product_code_generation_policy import (
    CodeRule,
    format_code,
    resolve_rule,
)
from backend.infrastructure.db.repositories.products.code_sequence_repository import (
    ProductCodeSequenceRepository,
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
    # Reglas: default PRD, tipo RAW_MATERIAL → MP, categoría 'cat-x' → CAT.
    c.execute("INSERT INTO product_code_generation_rules "
              "(id, scope_type, scope_value, prefix, padding, separator, active) "
              "VALUES ('r0','DEFAULT','','PRD',6,'-',1)")
    c.execute("INSERT INTO product_code_generation_rules "
              "(id, scope_type, scope_value, prefix, padding, separator, active) "
              "VALUES ('r1','PRODUCT_TYPE','RAW_MATERIAL','MP',6,'-',1)")
    c.execute("INSERT INTO product_code_generation_rules "
              "(id, scope_type, scope_value, prefix, padding, separator, active) "
              "VALUES ('r2','CATEGORY','cat-x','CAT',4,'-',1)")
    c.commit()
    yield c
    c.close()


# ── política pura ──────────────────────────────────────────────────────────
def test_format_pads_sequence():
    assert format_code(CodeRule(prefix="MP", padding=6), 1) == "MP-000001"
    assert format_code(CodeRule(prefix="MP", padding=6), 6) == "MP-000006"
    assert format_code(CodeRule(prefix="CAT", padding=4), 12) == "CAT-0012"


def test_resolve_precedence_category_beats_type():
    rules = {
        ("DEFAULT", ""): CodeRule("PRD"),
        ("PRODUCT_TYPE", "RAW_MATERIAL"): CodeRule("MP"),
        ("CATEGORY", "cat-x"): CodeRule("CAT"),
    }
    assert resolve_rule(rules, product_type="RAW_MATERIAL",
                        category_id="cat-x").prefix == "CAT"
    assert resolve_rule(rules, product_type="RAW_MATERIAL",
                        category_id=None).prefix == "MP"
    assert resolve_rule(rules, product_type="SERVICE",
                        category_id=None).prefix == "PRD"


def test_resolve_falls_back_to_prd_without_rules():
    assert resolve_rule({}, product_type="RAW_MATERIAL", category_id=None).prefix == "PRD"


# ── repositorio de secuencias ────────────────────────────────────────────────
def test_peek_does_not_consume(conn):
    repo = ProductCodeSequenceRepository(conn)
    assert repo.peek("MP") == 1
    assert repo.peek("MP") == 1  # peek repetido no avanza


def test_reserve_consumes_and_advances(conn):
    repo = ProductCodeSequenceRepository(conn)
    assert repo.reserve("MP") == 1
    assert repo.reserve("MP") == 2
    assert repo.peek("MP") == 3


# ── vista previa ─────────────────────────────────────────────────────────────
def test_preview_uses_type_rule_without_consuming(conn):
    svc = PreviewProductCodeQueryService(conn)
    assert svc.preview(product_type="RAW_MATERIAL") == "MP-000001"
    assert svc.preview(product_type="RAW_MATERIAL") == "MP-000001"  # no consume


def test_preview_uses_category_rule(conn):
    svc = PreviewProductCodeQueryService(conn)
    assert svc.preview(product_type="RAW_MATERIAL", category_id="cat-x") == "CAT-0001"


def test_reserve_next_code_helper(conn):
    assert reserve_next_code(conn, product_type="RAW_MATERIAL") == "MP-000001"
    assert reserve_next_code(conn, product_type="RAW_MATERIAL") == "MP-000002"


# ── alta con código automático ───────────────────────────────────────────────
def test_create_auto_generates_code(conn):
    cmd = CreateProductMasterCommand(
        operation_id="op1", code="", name="Bistec", product_type="RAW_MATERIAL",
        base_unit_id=_UNIT_ID, user_id="u1", auto_generate_code=True)
    r = CreateProductMasterUseCase(conn).execute(cmd)
    assert r.success
    row = conn.execute("SELECT code FROM products WHERE id=?", (r.product_id,)).fetchone()
    assert row["code"] == "MP-000001"


def test_auto_generate_is_gapless_and_sequential(conn):
    uc = CreateProductMasterUseCase(conn)
    codes = []
    for i in range(3):
        cmd = CreateProductMasterCommand(
            operation_id=f"op{i}", code="", name=f"P{i}", product_type="RAW_MATERIAL",
            base_unit_id=_UNIT_ID, user_id="u1", auto_generate_code=True)
        codes.append(uc.execute(cmd).product_id)
    got = [conn.execute("SELECT code FROM products WHERE id=?", (pid,)).fetchone()["code"]
           for pid in codes]
    assert got == ["MP-000001", "MP-000002", "MP-000003"]


def test_auto_generate_outbox_carries_real_code(conn):
    cmd = CreateProductMasterCommand(
        operation_id="op1", code="", name="Bistec", product_type="RAW_MATERIAL",
        base_unit_id=_UNIT_ID, user_id="u1", auto_generate_code=True)
    r = CreateProductMasterUseCase(conn).execute(cmd)
    payload = conn.execute("SELECT payload FROM product_outbox WHERE entity_id=?",
                           (r.product_id,)).fetchone()["payload"]
    assert json.loads(payload)["code"] == "MP-000001"


# ── override manual del código ───────────────────────────────────────────────
class _Checker:
    def __init__(self, granted):
        self._granted = set(granted)

    def has_permission(self, user_id, code):
        return code in self._granted


def test_manual_override_requires_permission(conn):
    # Sólo CREATE, sin OVERRIDE_CODE → el código manual se rechaza (fail-closed).
    auth = ProductsAuthorizationPolicy(_Checker({ProductPermissions.CREATE}))
    cmd = CreateProductMasterCommand(
        operation_id="op1", code="MANUAL-1", name="Producto X", product_type="RAW_MATERIAL",
        base_unit_id=_UNIT_ID, user_id="u1", auto_generate_code=False)
    with pytest.raises(ProductPermissionDeniedError):
        CreateProductMasterUseCase(conn, auth).execute(cmd)


def test_manual_override_allowed_with_permission_and_audited(conn):
    auth = ProductsAuthorizationPolicy(
        _Checker({ProductPermissions.CREATE, ProductPermissions.OVERRIDE_CODE}))
    cmd = CreateProductMasterCommand(
        operation_id="op1", code="MANUAL-1", name="Producto X", product_type="RAW_MATERIAL",
        base_unit_id=_UNIT_ID, user_id="u1", auto_generate_code=False)
    r = CreateProductMasterUseCase(conn, auth).execute(cmd)
    assert r.success
    row = conn.execute("SELECT code FROM products WHERE id=?", (r.product_id,)).fetchone()
    assert row["code"] == "MANUAL-1"
    audit = conn.execute(
        "SELECT action, after FROM product_audit_log WHERE entity_id=? AND action=?",
        (r.product_id, "CODE_OVERRIDE")).fetchone()
    assert audit is not None
    assert json.loads(audit["after"])["code"] == "MANUAL-1"


def test_auto_generate_does_not_audit_override(conn):
    cmd = CreateProductMasterCommand(
        operation_id="op1", code="", name="Producto X", product_type="RAW_MATERIAL",
        base_unit_id=_UNIT_ID, user_id="u1", auto_generate_code=True)
    r = CreateProductMasterUseCase(conn).execute(cmd)
    audit = conn.execute(
        "SELECT 1 FROM product_audit_log WHERE entity_id=? AND action='CODE_OVERRIDE'",
        (r.product_id,)).fetchone()
    assert audit is None
