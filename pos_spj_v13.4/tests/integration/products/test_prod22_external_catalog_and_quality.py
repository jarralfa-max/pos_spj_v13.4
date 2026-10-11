"""PROD-22 (pendientes) — catálogo externo utilizable y calidad de datos."""

from __future__ import annotations

import importlib
import os
import sqlite3

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from backend.application.products.queries.product_data_quality_query_service import (  # noqa: E402
    ProductDataQualityQueryService,
)
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema  # noqa: E402
from backend.infrastructure.db.schema.pricing_schema import create_pricing_schema  # noqa: E402
from backend.infrastructure.db.schema.products_schema import create_products_schema  # noqa: E402
from backend.infrastructure.product_catalogs.catalog_wiring import (  # noqa: E402
    build_default_registry,
)

M328 = importlib.import_module("migrations.standalone.328_external_catalog_source_and_reviewer")
ALL = {f"PRODUCTOS.{a}" for a in importlib.import_module(
    "migrations.standalone.324_seed_products_granular_permissions")._TODAS}


class _Session:
    def __init__(self, user_id, codes=ALL):
        self.user_id = user_id
        self._codes = set(codes)
        self.sucursal_id = None
        self.is_active = True

    def tiene_permiso(self, code):
        return code in self._codes


class _FakeOFF:
    """Cliente falso de Open Food Facts (sin red)."""

    def __init__(self, payload=None, fail=False):
        self.payload = payload or []
        self.fail = fail
        self.queries = []

    def fetch(self, query):
        self.queries.append(query)
        if self.fail:
            raise ConnectionError("sin conexión")
        return self.payload


_OFF_ROWS = [
    {"code": "7501055300075", "product_name": "Refresco de cola 600 ml", "brands": "Marca X",
     "categories": "Bebidas", "quantity": "600", "product_quantity_unit": "ml"},
    {"code": "7501000111206", "product_name": "Galletas marías", "brands": "Marca Y",
     "categories": "Galletas", "quantity": "170", "product_quantity_unit": "g"},
]


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
        INSERT INTO usuarios VALUES ('u-busca','Capturista','cap'), ('u-firma','Gerente','ger');
        INSERT INTO units_of_measure (id, code, name, dimension) VALUES
            ('u-pza','PZA','Pieza','COUNT'), ('u-kg','KG','Kilogramo','WEIGHT');
        INSERT INTO species (id, code, name, active) VALUES ('sp-pollo','AVE_POLLO','Ave',1);
    """)
    M328.run(c)
    yield c
    c.close()


def _presenter(conn, user_id, client):
    from frontend.desktop.modules.products.composition import (
        _Session as LiveSession,
        build_products_presenter,
    )
    live = _Session(user_id)
    return build_products_presenter(conn, LiveSession(live), live_session=live,
                                    external_registry=build_default_registry(client))


# ── catálogo externo ────────────────────────────────────────────────────────
def test_migration_registers_open_food_facts_once(conn):
    M328.run(conn)
    rows = conn.execute("SELECT code FROM external_catalog_sources").fetchall()
    assert [r[0] for r in rows] == ["OPEN_FOOD_FACTS"]


def test_search_review_approve_and_import_with_segregation(conn):
    client = _FakeOFF(_OFF_ROWS)
    searcher = _presenter(conn, "u-busca", client).external
    source = searcher.sources()[0]["id"]
    ok, message = searcher.search(source_id=source, query="refresco")
    assert ok and "2 resultado" in message
    records = {r["name"]: r for r in searcher.records()}
    cola = records["Refresco de cola 600 ml"]
    assert cola["status"] == "PENDING_REVIEW"

    # Quien lo trajo no lo aprueba (§39).
    ok, message = searcher.approve(cola["id"])
    assert not ok and "segundo usuario" in message

    signer = _presenter(conn, "u-firma", client).external
    assert signer.approve(cola["id"])[0]
    ok, message = signer.import_record(record_id=cola["id"], product_type="RESALE_PRODUCT",
                                       base_unit_id="u-pza", category_id=None)
    assert ok, message
    product = conn.execute("SELECT name, lifecycle_status FROM products").fetchone()
    assert tuple(product) == ("Refresco de cola 600 ml", "DRAFT")
    assert {r["status"] for r in signer.records() if r["id"] == cola["id"]} == {"IMPORTED"}


def test_searching_again_keeps_review_decisions_and_ids(conn):
    client = _FakeOFF(_OFF_ROWS)
    searcher = _presenter(conn, "u-busca", client).external
    signer = _presenter(conn, "u-firma", client).external
    source = searcher.sources()[0]["id"]
    searcher.search(source_id=source, query="refresco")
    cola = next(r for r in searcher.records() if r["barcode"] == "7501055300075")
    signer.approve(cola["id"])
    searcher.search(source_id=source, query="refresco")       # misma búsqueda otra vez
    again = [r for r in searcher.records() if r["barcode"] == "7501055300075"]
    assert len(again) == 1 and again[0]["id"] == cola["id"]
    assert again[0]["status"] == "APPROVED"                    # antes volvía a pendiente


def test_network_failure_is_reported_not_raised(conn):
    external = _presenter(conn, "u-busca", _FakeOFF(fail=True)).external
    ok, message = external.search(source_id=external.sources()[0]["id"], query="leche")
    assert not ok and message


def test_external_page_lists_and_gates_buttons(conn, qapp):
    from frontend.desktop.modules.products.pages.external_catalog_page import (
        ExternalCatalogPage,
    )
    presenter = _presenter(conn, "u-busca", _FakeOFF(_OFF_ROWS))
    page = ExternalCatalogPage(presenter)
    assert page.source.count() == 1 and page.btn_search.isEnabled()
    page.query.setText("galletas")
    page._search()
    assert page.table.rowCount() == 2
    page.table.selectRow(0)
    assert page.btn_approve.isEnabled() and not page.btn_import.isEnabled()


# ── calidad de datos ────────────────────────────────────────────────────────
def _product(conn, pid, ptype, **flags):
    cols = {"species_id": None, "category_id": None, "sellable": 1, "lifecycle_status": "ACTIVE",
            **flags}
    conn.execute(
        "INSERT INTO products (id, code, name, product_type, base_unit_id, lifecycle_status, "
        "species_id, category_id, sellable, expiration_controlled, catch_weight_enabled, "
        "quality_controlled) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (pid, f"C-{pid}", pid.title(), ptype, "u-kg", cols["lifecycle_status"],
         cols["species_id"], cols["category_id"], cols["sellable"],
         cols.get("expiration_controlled", 0), cols.get("catch_weight_enabled", 0),
         cols.get("quality_controlled", 0)))


def test_data_quality_uses_the_alert_rules_plus_completeness(conn):
    conn.execute("INSERT INTO product_categories (id, code, name) VALUES ('c1','POLLO','Pollo')")
    _product(conn, "pechuga", "PRIMARY_CUT", species_id="sp-pollo", category_id="c1",
             expiration_controlled=1, catch_weight_enabled=1, quality_controlled=1)
    _product(conn, "charola", "PACKAGING_MATERIAL", category_id="c1", sellable=0)
    conn.commit()
    report = {r["product_id"]: r for r in ProductDataQualityQueryService(conn).report()}
    assert set(report["pechuga"]["issues"]) == {
        "PERISHABLE_WITHOUT_SHELF_LIFE", "CATCH_WEIGHT_WITHOUT_RANGE",
        "MEAT_WITHOUT_QUALITY_PROFILE", "MEAT_WITHOUT_CLASSIFICATION",
        "SELLABLE_WITHOUT_IMAGE"}
    assert report["pechuga"]["score"] == 0
    assert "charola" not in report                 # completo: no aparece


def test_disabled_catch_weight_row_does_not_count_as_configured(conn):
    conn.execute("INSERT INTO product_categories (id, code, name) VALUES ('c1','POLLO','Pollo')")
    _product(conn, "pollo", "CARCASS", species_id="sp-pollo", category_id="c1",
             catch_weight_enabled=1, sellable=0)
    conn.execute("INSERT INTO product_catch_weight_config (product_id, enabled) "
                 "VALUES ('pollo', 0)")
    conn.commit()
    issues = ProductDataQualityQueryService(conn).report()[0]["issues"]
    assert "CATCH_WEIGHT_WITHOUT_RANGE" in issues


def test_data_quality_page_shows_summary_and_filter(conn, qapp):
    from frontend.desktop.modules.products.pages.data_quality_page import DataQualityPage
    conn.execute("INSERT INTO product_categories (id, code, name) VALUES ('c1','POLLO','Pollo')")
    _product(conn, "pechuga", "PRIMARY_CUT", species_id="sp-pollo", category_id="c1")
    conn.commit()
    page = DataQualityPage(_presenter(conn, "u-busca", _FakeOFF()))
    assert page.table.rowCount() == 1 and page.issue.count() >= 2
    page.issue.setCurrentIndex(page.issue.findData("SELLABLE_WITHOUT_IMAGE"))
    assert page.table.rowCount() == 1
