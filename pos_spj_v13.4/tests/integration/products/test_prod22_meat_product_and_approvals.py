"""PROD-22 (pendientes) — clasificación cárnica del producto, peso variable y
bandeja de aprobaciones técnicas."""

from __future__ import annotations

import importlib
import os
import sqlite3

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from backend.application.products.queries.product_approval_query_service import (  # noqa: E402
    ProductApprovalQueryService,
)
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema  # noqa: E402
from backend.infrastructure.db.schema.pricing_schema import create_pricing_schema  # noqa: E402
from backend.infrastructure.db.schema.products_schema import create_products_schema  # noqa: E402

ALL = {f"PRODUCTOS.{a}" for a in importlib.import_module(
    "migrations.standalone.324_seed_products_granular_permissions")._TODAS}


class _Session:
    def __init__(self, codes, user_id):
        self._codes = set(codes)
        self.user_id = user_id
        self.sucursal_id = None
        self.is_active = True

    def tiene_permiso(self, code):
        return code in self._codes


@pytest.fixture(scope="module")
def qapp():
    from PyQt5.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    create_products_schema(c)
    create_pricing_schema(c)
    create_inventory_schema(c)
    c.executescript("""
        CREATE TABLE IF NOT EXISTS usuarios (id TEXT PRIMARY KEY, nombre TEXT, usuario TEXT);
        INSERT INTO usuarios VALUES ('u-crea','Capturista','cap'), ('u-firma','Gerente','ger');
        INSERT INTO units_of_measure (id, code, name, dimension) VALUES
            ('u-kg','KG','Kilogramo','WEIGHT'), ('u-pza','PZA','Pieza','COUNT');
        INSERT INTO species (id, code, name, active) VALUES
            ('sp-pollo','AVE_POLLO','Ave — pollo',1), ('sp-res','BOVINO','Bovino',1);
        INSERT INTO products (id, code, name, product_type, base_unit_id, lifecycle_status,
                              species_id) VALUES
            ('p-pech','C-1','Pechuga','PRIMARY_CUT','u-kg','ACTIVE','sp-pollo'),
            ('p-canal','C-2','Canal','CARCASS','u-kg','ACTIVE','sp-pollo'),
            ('p-char','C-3','Charola','PACKAGING_MATERIAL','u-pza','ACTIVE',NULL);
    """)
    c.commit()
    yield c
    c.close()


def _presenter(conn, user_id="u-crea", codes=ALL):
    from frontend.desktop.modules.products.composition import (
        _Session as LiveSession,
        build_products_presenter,
    )
    live = _Session(codes, user_id)
    return build_products_presenter(conn, LiveSession(live), live_session=live)


def _classified_catalog(meat):
    meat.create_region(species_id="sp-pollo", code="PECHUGA", name="Pechuga")
    meat.create_region(species_id="sp-pollo", code="PIERNA", name="Pierna")
    regions = {r["code"]: r["id"] for r in meat.regions("sp-pollo")}
    meat.create_cut(species_id="sp-pollo", anatomical_region_id=regions["PECHUGA"],
                    code="PECH", name="Pechuga con hueso", cut_level="PRIMARY")
    cuts = {c["code"]: c["id"] for c in meat.cuts("sp-pollo")}
    return regions, cuts


# ── clasificación cárnica del producto ──────────────────────────────────────
def test_meat_product_is_classified_and_reclassification_needs_a_reason(conn):
    meat = _presenter(conn).meat
    regions, cuts = _classified_catalog(meat)
    ok, message = meat.classify_product(product_id="p-pech", meat_category="BONE_IN",
                                        anatomical_region_id=regions["PECHUGA"],
                                        cut_classification_id=cuts["PECH"])
    assert ok and message == "MEAT_PRODUCT_CLASSIFIED"
    info = meat.product_classification("p-pech")
    assert info["meat_category"] == "BONE_IN" and info["cut_classification_id"] == cuts["PECH"]

    ok, message = meat.classify_product(product_id="p-pech", meat_category="BONELESS",
                                        anatomical_region_id=regions["PECHUGA"],
                                        cut_classification_id=cuts["PECH"])
    assert not ok and "motivo" in message
    ok, _ = meat.classify_product(product_id="p-pech", meat_category="BONELESS",
                                  anatomical_region_id=regions["PECHUGA"],
                                  cut_classification_id=cuts["PECH"], reason="Deshuesada")
    assert ok
    row = conn.execute("SELECT action, reason FROM product_audit_log "
                       "WHERE action LIKE 'MEAT_PRODUCT_%' ORDER BY rowid DESC LIMIT 1").fetchone()
    assert tuple(row) == ("MEAT_PRODUCT_CLASSIFICATION_CHANGED", "Deshuesada")
    events = {r[0] for r in conn.execute("SELECT event_name FROM product_outbox")}
    assert {"MEAT_PRODUCT_CLASSIFIED", "MEAT_PRODUCT_CLASSIFICATION_CHANGED"} <= events


def test_cut_must_belong_to_the_chosen_region_and_species(conn):
    meat = _presenter(conn).meat
    regions, cuts = _classified_catalog(meat)
    ok, message = meat.classify_product(product_id="p-pech", meat_category=None,
                                        anatomical_region_id=regions["PIERNA"],
                                        cut_classification_id=cuts["PECH"])
    assert not ok and "región" in message
    meat.create_region(species_id="sp-res", code="LOMO", name="Lomo")
    res_region = meat.regions("sp-res")[0]["id"]
    ok, message = meat.classify_product(product_id="p-pech", meat_category=None,
                                        anatomical_region_id=res_region,
                                        cut_classification_id=None)
    assert not ok and "especie" in message


def test_non_meat_products_are_not_classified(conn):
    ok, message = _presenter(conn).meat.classify_product(
        product_id="p-char", meat_category="BONE_IN", anatomical_region_id=None,
        cut_classification_id=None)
    assert not ok and "cárnicos" in message


def test_classification_requires_its_permission(conn):
    meat = _presenter(conn, codes={"PRODUCTOS.ver", "PRODUCTOS.editar"}).meat
    assert not meat.can_classify_products
    ok, _ = meat.classify_product(product_id="p-pech", meat_category="BONE_IN",
                                  anatomical_region_id=None, cut_classification_id=None)
    assert not ok
    assert conn.execute("SELECT COUNT(*) FROM product_meat_classifications").fetchone()[0] == 0


# ── peso variable ───────────────────────────────────────────────────────────
def test_catch_weight_needs_a_real_range_when_enabled(conn):
    """Antes el caso de uso convertía un rango vacío en 0–0 y lo aceptaba."""
    meat = _presenter(conn).meat
    ok, message = meat.save_catch_weight(product_id="p-canal", enabled=True,
                                         nominal_unit_id="u-pza", weight_unit_id="u-kg")
    assert not ok and "rango" in message
    ok, _ = meat.save_catch_weight(product_id="p-canal", enabled=True,
                                   nominal_unit_id="u-pza", weight_unit_id="u-kg",
                                   minimum_weight="1.800", maximum_weight="2.600",
                                   average_weight="2.100", tolerance_pct="5")
    assert ok
    cw = meat.catch_weight("p-canal")
    assert cw["enabled"] == 1 and cw["minimum_weight"] == "1.800"


def test_disabling_catch_weight_without_units_respects_foreign_keys(conn):
    ok, message = _presenter(conn).meat.save_catch_weight(
        product_id="p-canal", enabled=False, nominal_unit_id="", weight_unit_id="")
    assert ok, message


# ── bandeja de aprobaciones ─────────────────────────────────────────────────
_OUT = [{"product_id": "p-pech", "output_type": "MAIN_PRODUCT",
         "expected_yield_pct": "100", "unit_id": "u-kg"}]


def test_approvals_worklist_and_segregation_of_duties(conn, qapp):
    from frontend.desktop.modules.products.pages.approvals_page import ApprovalsPage

    creator = _presenter(conn, "u-crea")
    assert creator.create_yield_profile(input_product_id="p-canal", name="Canal a cortes",
                                        tolerance_pct="2", outputs=_OUT)[0]
    pending = ProductApprovalQueryService(conn).pending()
    assert [(r["kind"], r["status"], r["product_name"], r["created_by_name"])
            for r in pending] == [("YIELD", "DRAFT", "Canal", "Capturista")]
    version_id = pending[0]["version_id"]

    page = ApprovalsPage(creator)
    page.table.selectRow(0)
    assert page.btn_submit.isEnabled() and not page.btn_approve.isEnabled()
    page.btn_submit.click()
    assert ProductApprovalQueryService(conn).pending()[0]["status"] == "UNDER_REVIEW"

    # Quien la creó no puede aprobarla (segregación, §39).
    page.table.selectRow(0)
    page.btn_approve.click()
    assert ProductApprovalQueryService(conn).pending()[0]["status"] == "UNDER_REVIEW"
    assert page.message.isVisibleTo(page) and page.message.property("state") == "error"

    signer = ApprovalsPage(_presenter(conn, "u-firma"))
    signer.table.selectRow(0)
    signer.btn_approve.click()
    assert ProductApprovalQueryService(conn).pending()[0]["status"] == "APPROVED"
    signer.table.selectRow(0)
    assert signer.btn_activate.isEnabled()
    signer.btn_activate.click()
    assert ProductApprovalQueryService(conn).pending() == []
    assert conn.execute("SELECT status FROM yield_profile_versions WHERE id=?",
                        (version_id,)).fetchone()[0] == "ACTIVE"


def test_products_view_lists_the_worklist(conn, qapp):
    from frontend.desktop.modules.products.composition import build_products_view
    titles = [t for _f, t in build_products_view(_presenter(conn))._specs]
    assert titles[:3] == ["Resumen", "Catálogo", "Aprobaciones técnicas"]


def test_meat_product_dialog_opens_with_species_filtered_cuts(conn, qapp):
    from frontend.desktop.modules.products.dialogs.meat_product_dialog import MeatProductDialog
    meat = _presenter(conn).meat
    regions, _cuts = _classified_catalog(meat)
    dialog = MeatProductDialog(meat, product_id="p-pech", product_name="Pechuga")
    assert dialog.region.count() == 3          # (Sin región) + Pechuga + Pierna
    dialog.region.setCurrentIndex(dialog.region.findData(regions["PIERNA"]))
    assert dialog.cut.count() == 1             # sólo (Sin corte): el corte es de Pechuga
    assert dialog._unit_code[dialog.weight_unit.currentData()] == "KG"
    assert dialog._unit_code[dialog.nominal_unit.currentData()] == "PZA"
