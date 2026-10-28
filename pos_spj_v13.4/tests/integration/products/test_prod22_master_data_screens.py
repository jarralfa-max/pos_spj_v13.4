"""PROD-22 — pantallas que faltaban sobre backend que ya existía.

* Catálogo con filtro de familia (cárnicos / internos / materiales…).
* Clasificación cárnica: especies, regiones anatómicas y cortes jerárquicos.
* Códigos de barras de un producto: un solo principal (el POS une por él).
* Perfiles de vida útil / calidad / logística.
* Bitácora de auditoría, sólo con su permiso.
* El catálogo cabe en el ancho real del shell.
"""

from __future__ import annotations

import os
import sqlite3

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from backend.application.products.authorization.permission_bridge import (  # noqa: E402
    SessionPermissionChecker,
    make_permission_checker,
)
from backend.application.products.authorization.policy import (  # noqa: E402
    ProductsAuthorizationPolicy,
)
from backend.application.products.permissions import ProductPermissions as P  # noqa: E402
from backend.application.products.queries.catalog_read_service import (  # noqa: E402
    ProductCatalogReadService,
)
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema  # noqa: E402
from backend.infrastructure.db.schema.pricing_schema import create_pricing_schema  # noqa: E402
from backend.infrastructure.db.schema.products_schema import create_products_schema  # noqa: E402
from backend.shared.ids import new_uuid  # noqa: E402


class _Session:
    def __init__(self, codes, user_id="u-1"):
        self._codes = set(codes)
        self.user_id = user_id
        self.sucursal_id = None
        self.is_active = True

    def tiene_permiso(self, code):
        return code in self._codes


ALL = {f"PRODUCTOS.{a}" for a in __import__(
    "importlib").import_module(
    "migrations.standalone.324_seed_products_granular_permissions")._TODAS}


@pytest.fixture(scope="module")
def qapp():
    from PyQt5.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_products_schema(c)
    create_pricing_schema(c)
    create_inventory_schema(c)
    c.executescript("""
        CREATE TABLE IF NOT EXISTS usuarios (id TEXT PRIMARY KEY, nombre TEXT, usuario TEXT);
        INSERT INTO usuarios VALUES ('u-1', 'Ana Dueña', 'ana');
        INSERT INTO units_of_measure (id, code, name, dimension) VALUES ('u-kg','KG','Kilogramo','WEIGHT');
        INSERT INTO species (id, code, name, active) VALUES ('sp-pollo','AVE_POLLO','Ave — pollo',1);
    """)
    for pid, name, ptype, internal in (("p-1", "Pechuga", "PRIMARY_CUT", 0),
                                       ("p-2", "Canal en proceso", "CARCASS", 1),
                                       ("p-3", "Charola", "PACKAGING_MATERIAL", 0)):
        c.execute("INSERT INTO products (id, code, name, product_type, base_unit_id, "
                  "lifecycle_status, internal_only, species_id) VALUES (?,?,?,?,?,?,?,?)",
                  (pid, f"C-{pid}", name, ptype, "u-kg", "ACTIVE", internal,
                   "sp-pollo" if ptype != "PACKAGING_MATERIAL" else None))
    c.commit()
    yield c
    c.close()


def _presenter(conn, codes=ALL):
    from frontend.desktop.modules.products.composition import (
        _Session as LiveSession,
        build_products_presenter,
    )
    live = _Session(codes)
    return build_products_presenter(conn, LiveSession(live), live_session=live)


# ── familia del catálogo ───────────────────────────────────────────────────
def test_catalog_family_filter(conn):
    svc = ProductCatalogReadService(conn)
    names = lambda fam: {r["name"] for r in svc.list_catalog(family=fam)}  # noqa: E731
    assert names("MEAT") == {"Pechuga", "Canal en proceso"}
    assert names("INTERNAL") == {"Canal en proceso"}
    assert names("MATERIALS") == {"Charola"}
    assert names(None) == {"Pechuga", "Canal en proceso", "Charola"}


# ── clasificación cárnica ──────────────────────────────────────────────────
def test_meat_classification_end_to_end(conn):
    meat = _presenter(conn).meat
    assert meat.create_region(species_id="sp-pollo", code="PECHUGA", name="Pechuga")[0]
    region = meat.regions("sp-pollo")[0]["id"]
    ok, _m = meat.create_cut(species_id="sp-pollo", anatomical_region_id=region,
                             code="PECH_HUESO", name="Pechuga con hueso",
                             cut_level="PRIMARY", bone_status="BONE_IN")
    assert ok
    parent = meat.cuts("sp-pollo")[0]["id"]
    assert meat.create_cut(species_id="sp-pollo", anatomical_region_id=region,
                           code="FILETE", name="Filete", cut_level="SECONDARY",
                           parent_cut_id=parent)[0]
    assert {c["name"] for c in meat.cuts("sp-pollo")} == {"Pechuga con hueso", "Filete"}
    assert meat.set_region_active(region, False)[0]
    assert meat.regions("sp-pollo")[0]["active"] in (0, False)
    actions = {r[0] for r in conn.execute("SELECT action FROM product_audit_log")}
    assert {"ANATOMICAL_REGION_CREATED", "CUT_CLASSIFICATION_CREATED"} <= actions


def test_meat_classification_is_denied_without_permission(conn):
    meat = _presenter(conn, codes={"PRODUCTOS.ver"}).meat
    assert not meat.can_manage_regions and not meat.can_manage_species
    ok, message = meat.create_region(species_id="sp-pollo", code="X", name="X")
    assert not ok and conn.execute("SELECT COUNT(*) FROM anatomical_regions").fetchone()[0] == 0


# ── códigos de barras ──────────────────────────────────────────────────────
def test_only_one_primary_barcode_per_product(conn):
    codes = _presenter(conn).codes_profiles
    assert codes.assign_barcode(product_id="p-1", value="7501234567893",
                                barcode_type="EAN", is_primary=True)[0]
    assert codes.assign_barcode(product_id="p-1", value="2001", barcode_type="PLU",
                                is_primary=True)[0]
    primaries = [b["value"] for b in codes.barcodes("p-1") if b["is_primary"]]
    assert primaries == ["2001"]


def test_reassigning_the_same_code_is_a_quiet_no_op(conn):
    codes = _presenter(conn).codes_profiles
    codes.assign_barcode(product_id="p-1", value="7501234567893", barcode_type="EAN")
    before = conn.execute("SELECT COUNT(*) FROM product_audit_log").fetchone()[0]
    ok, message = codes.assign_barcode(product_id="p-1", value="7501234567893",
                                       barcode_type="EAN")
    assert ok and "ya estaba" in message
    assert conn.execute("SELECT COUNT(*) FROM product_audit_log").fetchone()[0] == before


def test_invalid_check_digit_is_explained(conn):
    ok, message = _presenter(conn).codes_profiles.assign_barcode(
        product_id="p-1", value="7501234567890", barcode_type="EAN")
    assert not ok and "verificador" in message


def test_a_code_active_on_another_product_is_rejected(conn):
    codes = _presenter(conn).codes_profiles
    codes.assign_barcode(product_id="p-1", value="2001", barcode_type="PLU")
    ok, _message = codes.assign_barcode(product_id="p-3", value="2001", barcode_type="PLU")
    assert not ok


# ── perfiles ───────────────────────────────────────────────────────────────
def test_profiles_round_trip(conn):
    codes = _presenter(conn).codes_profiles
    assert codes.save_shelf_life(product_id="p-1", shelf_life_days=5,
                                 storage_condition="CHILLED")[0]
    assert codes.save_quality(product_id="p-1", inspection_required=True,
                              fat_pct_min="2", fat_pct_max="8")[0]
    assert codes.save_logistics(product_id="p-1", perishable=True, chilled=True,
                                storage_temp_min="0", storage_temp_max="4")[0]
    profiles = codes.profiles("p-1")
    assert profiles["shelf_life"]["shelf_life_days"] == 5
    assert str(profiles["quality"]["fat_pct_max"]) in ("8", "8.00")
    assert profiles["logistics"]["requires_cold_chain"] in (1, True)


# ── auditoría ──────────────────────────────────────────────────────────────
def test_audit_requires_its_own_permission(conn):
    _presenter(conn).codes_profiles.save_shelf_life(product_id="p-1", shelf_life_days=3)
    full = _presenter(conn).audit
    rows = full.entries()
    assert rows and rows[0]["action_label"] == "Vida útil"
    assert rows[0]["subject"] == "C-p-1 · Pechuga" and rows[0]["user_name"] == "Ana Dueña"
    cashier = _presenter(conn, codes={"PRODUCTOS.ver"}).audit
    assert not cashier.can_view and cashier.entries() == []


# ── pantallas ──────────────────────────────────────────────────────────────
def test_products_view_has_the_new_sections_and_fits_the_shell(conn, qapp):
    from frontend.desktop.modules.products.composition import build_products_view
    view = build_products_view(_presenter(conn))
    titles = [title for _factory, title in view._specs]
    assert {"Clasificación cárnica", "Auditoría"} <= set(titles)
    catalog_index = titles.index("Catálogo")
    view.nav.select(catalog_index)
    page = view.stack.widget(catalog_index).layout().itemAt(0).widget()
    # Antes: 11 botones en una fila (no cabía a 1366×768 e imponía scroll
    # horizontal a todo el módulo). Ahora 5 acciones + «Más acciones».
    # (Sin aserción en píxeles: la plataforma offscreen infla las fuentes.)
    toolbar_buttons = [b for b in (page.btn_new, page.btn_edit, page.btn_submit,
                                   page.btn_activate, page.btn_more)]
    assert len(toolbar_buttons) == 5 and page.btn_more.menu() is not None
    assert len(page.more_menu.actions()) >= 9
    assert page.family.count() >= 5
    assert page.family.minimumContentsLength() == 14


def test_catalog_actions_without_selection_explain_instead_of_doing_nothing(
        conn, qapp, monkeypatch):
    from frontend.desktop.components.dialogs import MessageDialog

    from frontend.desktop.modules.products.pages.product_catalog_page import (
        ProductCatalogPage,
    )
    shown = []
    monkeypatch.setattr(MessageDialog, "information",
                        lambda *a, **k: shown.append(a[2]))
    page = ProductCatalogPage(_presenter(conn))
    page.table.clearSelection()
    page._open_barcodes()
    page._open_profiles()
    assert shown == ["Selecciona un producto del catálogo."] * 2


def test_activate_button_needs_activate_permission_not_edit(conn, qapp):
    from frontend.desktop.modules.products.pages.product_catalog_page import (
        ProductCatalogPage,
    )
    page = ProductCatalogPage(_presenter(conn, codes={"PRODUCTOS.ver", "PRODUCTOS.editar"}))
    assert page.btn_edit.isEnabled() and not page.btn_activate.isEnabled()


def test_master_data_dialogs_open(conn, qapp):
    from frontend.desktop.modules.products.dialogs.barcodes_dialog import BarcodesDialog
    from frontend.desktop.modules.products.dialogs.profiles_dialog import ProfilesDialog
    from frontend.desktop.modules.products.pages.audit_page import ProductAuditPage
    from frontend.desktop.modules.products.pages.meat_classification_page import (
        MeatClassificationPage,
    )
    presenter = _presenter(conn)
    presenter.codes_profiles.assign_barcode(product_id="p-1", value="2001",
                                            barcode_type="PLU")
    assert BarcodesDialog(presenter.codes_profiles, product_id="p-1",
                          product_name="Pechuga").barcodes_table.rowCount() == 1
    ProfilesDialog(presenter.codes_profiles, product_id="p-1", product_name="Pechuga")
    meat_page = MeatClassificationPage(presenter)
    assert meat_page.species_combo.count() == 1
    assert ProductAuditPage(presenter).table.rowCount() >= 1
