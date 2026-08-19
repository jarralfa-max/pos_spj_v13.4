"""PROD-3 — clasificación cárnica: especies, regiones anatómicas y cortes.

Antes de esta fase, `Species`/`AnatomicalRegion`/`CutClassification` tenían
entidades de dominio + policies + jerarquía validados, pero CERO casos de uso
reales (`Species`/`AnatomicalRegion`/`CutClassification` nunca se construían
fuera de sus propios archivos de entidad, confirmado por grep) — las especies
sólo llegaban por semilla de migración (169) y regiones/cortes no tenían
ninguna vía de alta. Estos tests prueban que el catálogo ahora es
gestionable de punta a punta, no sólo que las entidades individuales validan
correctamente.
"""

from __future__ import annotations

import sqlite3

import pytest

from backend.application.products.authorization.policy import ProductsAuthorizationPolicy
from backend.application.products.commands.product_meat_classification_commands import (
    CreateAnatomicalRegionCommand,
    CreateCutClassificationCommand,
    CreateSpeciesCommand,
    SetAnatomicalRegionActiveCommand,
    SetCutClassificationActiveCommand,
    SetSpeciesActiveCommand,
)
from backend.application.products.permissions import ProductPermissions
from backend.application.products.queries.meat_classification_query_service import (
    MeatClassificationQueryService,
)
from backend.application.products.use_cases.product_meat_classification_use_cases import (
    CreateAnatomicalRegionUseCase,
    CreateCutClassificationUseCase,
    CreateSpeciesUseCase,
    SetAnatomicalRegionActiveUseCase,
    SetCutClassificationActiveUseCase,
    SetSpeciesActiveUseCase,
)
from backend.domain.products.exceptions import ProductPermissionDeniedError
from backend.infrastructure.db.schema.products_schema import create_products_schema

_P = ProductPermissions


class _Checker:
    def __init__(self, granted):
        self._granted = set(granted)

    def has_permission(self, user_id, code):
        return code in self._granted


_ALL = ProductsAuthorizationPolicy(_Checker({
    _P.SPECIES_MANAGE, _P.MEAT_CLASSIFICATION_MANAGE, _P.CUTS_MANAGE}))


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_products_schema(c)
    c.commit()
    yield c
    c.close()


def _species(conn, code="BOVINO", name="Bovino (res)"):
    return CreateSpeciesUseCase(conn, _ALL).execute(
        CreateSpeciesCommand(operation_id="op", code=code, name=name, user_id="u1"))


def _region(conn, species_id, code="LOMO", name="Lomo"):
    return CreateAnatomicalRegionUseCase(conn, _ALL).execute(
        CreateAnatomicalRegionCommand(operation_id="op", species_id=species_id,
                                      code=code, name=name, user_id="u1"))


class TestSpecies:
    def test_create_species(self, conn):
        r = _species(conn)
        assert r.success and r.entity_id
        rows = conn.execute("SELECT code, name, active FROM species WHERE id=?",
                            (r.entity_id,)).fetchall()
        assert len(rows) == 1 and rows[0]["code"] == "BOVINO" and rows[0]["active"] == 1

    def test_duplicate_code_rejected(self, conn):
        _species(conn, code="BOVINO")
        r2 = _species(conn, code="bovino")  # normaliza a mayúsculas
        assert not r2.success and "existe" in r2.message.lower()

    def test_create_requires_permission(self, conn):
        no_perm = ProductsAuthorizationPolicy(_Checker(set()))
        with pytest.raises(ProductPermissionDeniedError):
            CreateSpeciesUseCase(conn, no_perm).execute(
                CreateSpeciesCommand(operation_id="op", code="X", name="X"))

    def test_deactivate_species(self, conn):
        r = _species(conn)
        toggled = SetSpeciesActiveUseCase(conn, _ALL).execute(
            SetSpeciesActiveCommand(operation_id="op2", species_id=r.entity_id,
                                    active=False, user_id="u1"))
        assert toggled.success
        row = conn.execute("SELECT active FROM species WHERE id=?",
                           (r.entity_id,)).fetchone()
        assert row["active"] == 0

    def test_species_creation_writes_audit_entry(self, conn):
        r = _species(conn)
        row = conn.execute(
            "SELECT action FROM product_audit_log WHERE entity_id=?",
            (r.entity_id,)).fetchone()
        assert row["action"] == "SPECIES_CREATED"


class TestAnatomicalRegion:
    def test_create_region_under_species(self, conn):
        sp = _species(conn)
        r = _region(conn, sp.entity_id)
        assert r.success
        row = conn.execute("SELECT species_id, code FROM anatomical_regions WHERE id=?",
                           (r.entity_id,)).fetchone()
        assert row["species_id"] == sp.entity_id and row["code"] == "LOMO"

    def test_region_requires_existing_species(self, conn):
        r = _region(conn, "does-not-exist")
        assert not r.success and "especie" in r.message.lower()

    def test_duplicate_code_scoped_per_species(self, conn):
        sp1 = _species(conn, code="BOVINO")
        sp2 = _species(conn, code="PORCINO")
        r1 = _region(conn, sp1.entity_id, code="LOMO")
        r2 = _region(conn, sp2.entity_id, code="LOMO")  # misma clave, otra especie: OK
        r3 = _region(conn, sp1.entity_id, code="LOMO")  # misma especie: rechazado
        assert r1.success and r2.success
        assert not r3.success and "existe" in r3.message.lower()

    def test_deactivate_region(self, conn):
        sp = _species(conn)
        r = _region(conn, sp.entity_id)
        toggled = SetAnatomicalRegionActiveUseCase(conn, _ALL).execute(
            SetAnatomicalRegionActiveCommand(operation_id="op2", region_id=r.entity_id,
                                             active=False, user_id="u1"))
        assert toggled.success


class TestCutClassification:
    def _cut(self, conn, species_id, region_id, *, code="LOM-01", name="Lomo entero",
             cut_level="PRIMARY", parent_cut_id=None):
        return CreateCutClassificationUseCase(conn, _ALL).execute(
            CreateCutClassificationCommand(
                operation_id="op", species_id=species_id,
                anatomical_region_id=region_id, code=code, name=name,
                cut_level=cut_level, parent_cut_id=parent_cut_id, user_id="u1"))

    def test_create_primary_cut(self, conn):
        sp = _species(conn)
        rg = _region(conn, sp.entity_id)
        r = self._cut(conn, sp.entity_id, rg.entity_id)
        assert r.success
        row = conn.execute("SELECT cut_level FROM cut_classifications WHERE id=?",
                           (r.entity_id,)).fetchone()
        assert row["cut_level"] == "PRIMARY"

    def test_region_must_belong_to_species(self, conn):
        sp1 = _species(conn, code="BOVINO")
        sp2 = _species(conn, code="PORCINO")
        rg_of_sp2 = _region(conn, sp2.entity_id)
        r = self._cut(conn, sp1.entity_id, rg_of_sp2.entity_id)
        assert not r.success and "especie" in r.message.lower()

    def test_child_cut_under_valid_parent(self, conn):
        sp = _species(conn)
        rg = _region(conn, sp.entity_id)
        parent = self._cut(conn, sp.entity_id, rg.entity_id, code="LOM-01",
                           cut_level="PRIMARY")
        child = self._cut(conn, sp.entity_id, rg.entity_id, code="LOM-01-A",
                          cut_level="SECONDARY", parent_cut_id=parent.entity_id)
        assert child.success

    def test_child_cut_cross_species_parent_rejected(self, conn):
        sp1 = _species(conn, code="BOVINO")
        sp2 = _species(conn, code="PORCINO")
        rg1 = _region(conn, sp1.entity_id)
        rg2 = _region(conn, sp2.entity_id)
        parent = self._cut(conn, sp1.entity_id, rg1.entity_id, code="LOM-01",
                           cut_level="PRIMARY")
        child = self._cut(conn, sp2.entity_id, rg2.entity_id, code="LOM-01-A",
                          cut_level="SECONDARY", parent_cut_id=parent.entity_id)
        assert not child.success and "especie" in child.message.lower()

    def test_child_cut_same_or_higher_level_rejected(self, conn):
        sp = _species(conn)
        rg = _region(conn, sp.entity_id)
        parent = self._cut(conn, sp.entity_id, rg.entity_id, code="LOM-01",
                           cut_level="SECONDARY")
        same_level = self._cut(conn, sp.entity_id, rg.entity_id, code="LOM-02",
                               cut_level="SECONDARY", parent_cut_id=parent.entity_id)
        assert not same_level.success and "nivel" in same_level.message.lower()

    def test_deactivate_cut(self, conn):
        sp = _species(conn)
        rg = _region(conn, sp.entity_id)
        r = self._cut(conn, sp.entity_id, rg.entity_id)
        toggled = SetCutClassificationActiveUseCase(conn, _ALL).execute(
            SetCutClassificationActiveCommand(operation_id="op2", cut_id=r.entity_id,
                                              active=False, user_id="u1"))
        assert toggled.success
        row = conn.execute("SELECT status FROM cut_classifications WHERE id=?",
                           (r.entity_id,)).fetchone()
        assert row["status"] == "INACTIVE"


class TestMeatClassificationQueryService:
    def test_region_and_cut_options(self, conn):
        sp = _species(conn)
        rg = CreateAnatomicalRegionUseCase(conn, _ALL).execute(
            CreateAnatomicalRegionCommand(operation_id="op", species_id=sp.entity_id,
                                          code="LOMO", name="Lomo", user_id="u1"))
        CreateCutClassificationUseCase(conn, _ALL).execute(
            CreateCutClassificationCommand(
                operation_id="op", species_id=sp.entity_id,
                anatomical_region_id=rg.entity_id, code="LOM-01", name="Lomo entero",
                cut_level="PRIMARY", user_id="u1"))
        svc = MeatClassificationQueryService(conn)
        regions = svc.region_options(sp.entity_id)
        cuts = svc.cut_options(sp.entity_id)
        assert regions == [{"id": rg.entity_id, "code": "LOMO", "label": "Lomo"}]
        assert len(cuts) == 1 and cuts[0]["code"] == "LOM-01"

    def test_inactive_excluded_by_default(self, conn):
        sp = _species(conn)
        rg = _region(conn, sp.entity_id)
        SetAnatomicalRegionActiveUseCase(conn, _ALL).execute(
            SetAnatomicalRegionActiveCommand(operation_id="op2", region_id=rg.entity_id,
                                             active=False, user_id="u1"))
        svc = MeatClassificationQueryService(conn)
        assert svc.region_options(sp.entity_id) == []
        assert svc.region_options(sp.entity_id, active_only=False) != []
