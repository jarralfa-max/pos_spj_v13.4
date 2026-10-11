"""PROD-22 — exigencias adicionales para activar (§45, decisión «sólo endurecer»).

Las prohibiciones del §7 son fijas; estas exigencias se encienden en Productos →
Configuración y bloquean la ACTIVACIÓN (el borrador sí se guarda). La pantalla
y el backend usan la misma regla.
"""

from __future__ import annotations

import importlib
import os
import sqlite3

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from backend.application.products.queries.product_activation_readiness_query_service import (  # noqa: E402,E501
    ProductActivationReadinessQueryService,
)
from backend.application.products.use_cases.product_lifecycle_use_cases import (  # noqa: E402
    ActivateProductUseCase,
    SubmitProductUseCase,
)
from backend.infrastructure.db.schema.products_schema import create_products_schema  # noqa: E402

ALL = {f"PRODUCTOS.{a}" for a in importlib.import_module(
    "migrations.standalone.324_seed_products_granular_permissions")._TODAS}


class _Session:
    def __init__(self, user_id="u-dueno", codes=ALL):
        self.user_id = user_id
        self._codes = set(codes)
        self.sucursal_id = None
        self.is_active = True

    def tiene_permiso(self, code):
        return code in self._codes


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    from tests.integration._governed_settings import ensure_governance
    create_products_schema(c)
    ensure_governance(c)
    c.executescript("""
        CREATE TABLE IF NOT EXISTS usuarios (id TEXT PRIMARY KEY, nombre TEXT, usuario TEXT,
                                             rol TEXT, activo INTEGER DEFAULT 1);
        INSERT INTO units_of_measure (id, code, name, dimension) VALUES
            ('u-kg','KG','Kilogramo','WEIGHT');
        INSERT INTO product_categories (id, code, name) VALUES ('c1','POLLO','Pollo');
        INSERT INTO species (id, code, name, active) VALUES ('sp','AVE_POLLO','Ave',1);
        INSERT INTO products (id, code, name, product_type, base_unit_id, lifecycle_status,
                              species_id, category_id, expiration_controlled,
                              catch_weight_enabled, created_by)
        VALUES ('p1','C-1','Pechuga','PRIMARY_CUT','u-kg','DRAFT','sp','c1',1,1,'creador');
    """)
    c.commit()
    yield c
    c.close()


def _settings(conn):
    from frontend.desktop.modules.products.composition import (
        _Session as LiveSession,
        build_products_presenter,
    )
    live = _Session()
    return build_products_presenter(conn, LiveSession(live), live_session=live).settings


def _activate(conn):
    SubmitProductUseCase(conn).execute(product_id="p1", user_id="creador")
    return ActivateProductUseCase(conn).execute(product_id="p1", user_id="aprobador")


def test_requirements_off_by_default_change_nothing(conn):
    assert ProductActivationReadinessQueryService(conn).readiness("p1").ready
    assert _activate(conn).success


def test_each_enabled_requirement_blocks_activation_until_completed(conn):
    assert _settings(conn).save(requirements={
        "meat_classification": True, "shelf_life": True, "quality_profile": True,
        "catch_weight_range": True})[0]
    readiness = ProductActivationReadinessQueryService(conn).readiness("p1")
    assert not readiness.ready and len(readiness.missing) == 4
    result = _activate(conn)
    assert not result.success and "Vida útil" in result.message
    assert conn.execute("SELECT lifecycle_status FROM products WHERE id='p1'"
                        ).fetchone()[0] == "UNDER_REVIEW"

    conn.executescript("""
        INSERT INTO product_meat_classifications (product_id, meat_category)
            VALUES ('p1','BONE_IN');
        INSERT INTO product_shelf_life_profiles (id, product_id, shelf_life_days)
            VALUES ('s1','p1',5);
        INSERT INTO product_quality_profiles (product_id) VALUES ('p1');
        INSERT INTO product_catch_weight_config (product_id, enabled, nominal_unit_id,
            weight_unit_id, minimum_weight, maximum_weight)
            VALUES ('p1',1,'u-kg','u-kg','0.8','1.4');
    """)
    assert ActivateProductUseCase(conn).execute(product_id="p1", user_id="aprobador").success


def test_requirement_only_applies_where_it_makes_sense(conn):
    """Vida útil sólo a perecederos; clasificación/calidad sólo a cárnicos."""
    _settings(conn).save(requirements={"shelf_life": True, "meat_classification": True,
                                       "quality_profile": True})
    conn.execute("INSERT INTO products (id, code, name, product_type, base_unit_id, "
                 "lifecycle_status, category_id) VALUES ('p2','C-2','Charola',"
                 "'PACKAGING_MATERIAL','u-kg','DRAFT','c1')")
    assert ProductActivationReadinessQueryService(conn).readiness("p2").ready


def test_fixed_rules_cannot_be_switched_off(conn):
    """§7: especie en cárnicos no es un parámetro (no existe la clave)."""
    from backend.application.settings.catalog import CATALOG_BY_KEY
    keys = {k for k in CATALOG_BY_KEY if k.startswith("products.")}
    assert not any("species" in k or "approval" in k or "segregation" in k for k in keys)


@pytest.fixture(scope="module")
def qapp():
    from PyQt5.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_settings_page_shows_and_saves_requirements(conn, qapp):
    from frontend.desktop.modules.products.composition import (
        _Session as LiveSession,
        build_products_presenter,
    )
    from frontend.desktop.modules.products.pages.settings_page import ProductSettingsPage
    live = _Session()
    page = ProductSettingsPage(build_products_presenter(conn, LiveSession(live),
                                                       live_session=live))
    page.req_checks["shelf_life"].setChecked(True)
    page._save_requirements()
    assert page.message.property("state") == "success"
    assert not ProductActivationReadinessQueryService(conn).readiness("p1").ready
