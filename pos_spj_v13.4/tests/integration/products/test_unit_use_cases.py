"""PROD-5 — unidades, conversiones y peso variable.

Antes de esta fase, `UnitOfMeasure`/`ProductUnitConversion`/
`CatchWeightConfiguration` tenían entidades de dominio + `UnitRepository` +
`unit_conversion_policy.detect_cycle` (grafo con detección de ciclos
multi-hop) completamente construidos pero con CERO casos de uso reales
(confirmado por grep: sin consumidores fuera de sus propios archivos) — las
unidades sólo llegaban por semilla de migración (155). Estos tests prueban
que el catálogo ahora es gestionable de punta a punta, incluida la detección
de ciclos multi-hop ejercida por primera vez a través de un caso de uso real.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from backend.application.products.authorization.policy import ProductsAuthorizationPolicy
from backend.application.products.commands.product_unit_commands import (
    CreateUnitCommand,
    CreateUnitConversionCommand,
    SetCatchWeightConfigCommand,
    SetUnitActiveCommand,
)
from backend.application.products.permissions import ProductPermissions
from backend.application.products.use_cases.product_unit_use_cases import (
    CreateUnitConversionUseCase,
    CreateUnitUseCase,
    SetCatchWeightConfigUseCase,
    SetUnitActiveUseCase,
)
from backend.domain.products.exceptions import ProductPermissionDeniedError
from backend.infrastructure.db.repositories.products.unit_repository import (
    UnitRepository,
)
from backend.infrastructure.db.schema.products_schema import create_products_schema

_P = ProductPermissions


class _Checker:
    def __init__(self, granted):
        self._granted = set(granted)

    def has_permission(self, user_id, code):
        return code in self._granted


_ALL = ProductsAuthorizationPolicy(_Checker({
    _P.UNITS_MANAGE, _P.CONVERSIONS_MANAGE}))


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_products_schema(c)
    c.commit()
    yield c
    c.close()


def _unit(conn, code="KG", name="Kilogramo", dimension="WEIGHT"):
    return CreateUnitUseCase(conn, _ALL).execute(
        CreateUnitCommand(operation_id="op", code=code, name=name,
                          dimension=dimension, user_id="u1"))


class TestUnits:
    def test_create_unit(self, conn):
        r = _unit(conn)
        assert r.success and r.entity_id
        row = conn.execute("SELECT code, dimension, active FROM units_of_measure "
                           "WHERE id=?", (r.entity_id,)).fetchone()
        assert row["code"] == "KG" and row["dimension"] == "WEIGHT" and row["active"] == 1

    def test_duplicate_code_rejected(self, conn):
        _unit(conn, code="KG")
        r2 = _unit(conn, code="kg", name="otro")
        assert not r2.success and "existe" in r2.message.lower()

    def test_create_requires_permission(self, conn):
        no_perm = ProductsAuthorizationPolicy(_Checker(set()))
        with pytest.raises(ProductPermissionDeniedError):
            CreateUnitUseCase(conn, no_perm).execute(
                CreateUnitCommand(operation_id="op", code="X", name="X",
                                  dimension="WEIGHT"))

    def test_invalid_dimension_rejected(self, conn):
        r = _unit(conn, dimension="NOT_A_DIMENSION")
        assert not r.success

    def test_deactivate_unit(self, conn):
        r = _unit(conn)
        toggled = SetUnitActiveUseCase(conn, _ALL).execute(
            SetUnitActiveCommand(operation_id="op2", unit_id=r.entity_id,
                                 active=False, user_id="u1"))
        assert toggled.success
        row = conn.execute("SELECT active FROM units_of_measure WHERE id=?",
                           (r.entity_id,)).fetchone()
        assert row["active"] == 0

    def test_unit_creation_writes_audit_entry(self, conn):
        r = _unit(conn)
        row = conn.execute("SELECT action FROM product_audit_log WHERE entity_id=?",
                           (r.entity_id,)).fetchone()
        assert row["action"] == "UNIT_CREATED"


class TestUnitConversions:
    def test_create_conversion(self, conn):
        kg = _unit(conn, code="KG", dimension="WEIGHT")
        caja = _unit(conn, code="CAJA", dimension="PACKAGE")
        r = CreateUnitConversionUseCase(conn, _ALL).execute(
            CreateUnitConversionCommand(operation_id="op", from_unit_id=caja.entity_id,
                                        to_unit_id=kg.entity_id, factor="20",
                                        user_id="u1"))
        assert r.success
        row = conn.execute("SELECT factor FROM product_unit_conversions WHERE id=?",
                           (r.entity_id,)).fetchone()
        assert Decimal(row["factor"]) == Decimal("20")

    def test_conversion_requires_existing_units(self, conn):
        kg = _unit(conn)
        r = CreateUnitConversionUseCase(conn, _ALL).execute(
            CreateUnitConversionCommand(operation_id="op", from_unit_id="nope",
                                        to_unit_id=kg.entity_id, factor="1",
                                        user_id="u1"))
        assert not r.success and "no existe" in r.message.lower()

    def test_multi_hop_cycle_rejected(self, conn):
        # A -> B -> C -> A cierra un ciclo; la 3a arista debe rechazarse.
        a = _unit(conn, code="A", dimension="OTHER")
        b = _unit(conn, code="B", dimension="OTHER")
        c = _unit(conn, code="C", dimension="OTHER")
        uc = CreateUnitConversionUseCase(conn, _ALL)
        r1 = uc.execute(CreateUnitConversionCommand(
            operation_id="op1", from_unit_id=a.entity_id, to_unit_id=b.entity_id,
            factor="2", user_id="u1"))
        r2 = uc.execute(CreateUnitConversionCommand(
            operation_id="op2", from_unit_id=b.entity_id, to_unit_id=c.entity_id,
            factor="3", user_id="u1"))
        r3 = uc.execute(CreateUnitConversionCommand(
            operation_id="op3", from_unit_id=c.entity_id, to_unit_id=a.entity_id,
            factor="4", user_id="u1"))
        assert r1.success and r2.success
        assert not r3.success and "ciclo" in r3.message.lower()
        # el ciclo nunca se persistió
        rows = conn.execute("SELECT COUNT(*) AS n FROM product_unit_conversions"
                            ).fetchone()
        assert rows["n"] == 2

    def test_conversion_requires_permission(self, conn):
        kg = _unit(conn, code="KG")
        caja = _unit(conn, code="CAJA", dimension="PACKAGE")
        no_perm = ProductsAuthorizationPolicy(_Checker(set()))
        with pytest.raises(ProductPermissionDeniedError):
            CreateUnitConversionUseCase(conn, no_perm).execute(
                CreateUnitConversionCommand(
                    operation_id="op", from_unit_id=caja.entity_id,
                    to_unit_id=kg.entity_id, factor="20"))


class TestCatchWeightConfig:
    def test_set_catch_weight_config(self, conn):
        pza = _unit(conn, code="PZA", dimension="COUNT")
        kg = _unit(conn, code="KG", dimension="WEIGHT")
        r = SetCatchWeightConfigUseCase(conn, _ALL).execute(
            SetCatchWeightConfigCommand(
                operation_id="op", product_id="prod-1", enabled=True,
                nominal_unit_id=pza.entity_id, weight_unit_id=kg.entity_id,
                minimum_weight="0.8", maximum_weight="1.4", average_weight="1.1",
                tolerance_pct="5", user_id="u1"))
        assert r.success
        cfg = UnitRepository(conn).get_catch_weight("prod-1")
        assert cfg.enabled and cfg.minimum_weight == Decimal("0.8")
        assert cfg.price_basis.value == "PER_KILOGRAM"

    def test_min_greater_than_max_rejected(self, conn):
        pza = _unit(conn, code="PZA", dimension="COUNT")
        kg = _unit(conn, code="KG", dimension="WEIGHT")
        r = SetCatchWeightConfigUseCase(conn, _ALL).execute(
            SetCatchWeightConfigCommand(
                operation_id="op", product_id="prod-1", enabled=True,
                nominal_unit_id=pza.entity_id, weight_unit_id=kg.entity_id,
                minimum_weight="2", maximum_weight="1", user_id="u1"))
        assert not r.success and "máximo" in r.message.lower()

    def test_disabled_config_does_not_require_range(self, conn):
        r = SetCatchWeightConfigUseCase(conn, _ALL).execute(
            SetCatchWeightConfigCommand(
                operation_id="op", product_id="prod-1", enabled=False, user_id="u1"))
        assert r.success
