"""FASE 3 Compras (2026-09-25): unidades de compra desde Productos + compra rápida
que se VE guardar + búsqueda por la sucursal del documento.

* Unidad de inventario y factor los decide el maestro de Productos; el caso de uso
  ignora lo que mande la pantalla y rechaza una presentación no configurada.
* El evento de recepción manda costo por unidad de INVENTARIO (antes mandaba la
  cantidad convertida con el costo de la unidad de compra: 2 cajas de 20 kg a
  $400 entraban como 40 kg a $400/kg).
* El diálogo ya no tiene "Producto por peso" ni "Factor de conversión".
* Tras confirmar, la tabla se vacía (antes quedaba pintada con la compra ya
  registrada: "no pasa nada").
"""

import json
import os
import sqlite3
from decimal import Decimal

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt5.QtWidgets", exc_type=ImportError)

from PyQt5.QtWidgets import QApplication, QCheckBox, QLabel  # noqa: E402

from backend.application.procurement.permissions import ALL_PURCHASE_PERMISSIONS  # noqa: E402
from backend.infrastructure.db.schema.document_output_schema import (  # noqa: E402
    create_document_numbering_schema,
)
from backend.infrastructure.db.schema.procurement_schema import (  # noqa: E402
    create_procurement_schema,
)
from frontend.desktop.modules.purchasing.dialogs import direct_purchase_dialogs as dialogs  # noqa: E402
from frontend.desktop.modules.purchasing.direct_purchase_routes import (  # noqa: E402
    build_direct_purchase_presenter,
)
from frontend.desktop.modules.purchasing.direct_purchase_view_models import CartLineVM  # noqa: E402
from frontend.desktop.modules.purchasing.pages.direct_purchase_create_page import (  # noqa: E402
    DirectPurchaseCreatePage,
)
from tests.integration._supplier_cutover import apply_supplier_cutover  # noqa: E402
from tests.integration.procurement._purchase_context import seed_purchase_context  # noqa: E402


class Session:
    is_active = True
    user_id = "user-1"
    active_branch_id = "br-1"
    active_warehouse_id = ""

    def tiene_permiso(self, code):
        return code in ALL_PURCHASE_PERMISSIONS


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    create_procurement_schema(c)
    create_document_numbering_schema(c)
    c.execute("CREATE TABLE proveedores(id TEXT PRIMARY KEY, nombre TEXT, activo INTEGER)")
    c.execute("INSERT INTO proveedores VALUES ('sup-1','Proveedor Uno',1)")
    apply_supplier_cutover(c)
    seed_purchase_context(c)
    c.execute("CREATE TABLE sucursales (id TEXT PRIMARY KEY, nombre TEXT, activa INTEGER)")
    c.execute("INSERT INTO sucursales VALUES ('br-1','Sucursal Uno',1)")
    c.execute("CREATE TABLE usuarios_sucursales (usuario_id TEXT, sucursal_id TEXT)")
    c.execute("INSERT INTO usuarios_sucursales VALUES ('user-1','br-1')")
    # Maestro de unidades de Productos: pollo en KG con presentación CAJA de 20 kg.
    c.execute("CREATE TABLE units_of_measure (id TEXT PRIMARY KEY, code TEXT, name TEXT,"
              " dimension TEXT, active INTEGER DEFAULT 1)")
    c.executemany("INSERT INTO units_of_measure (id, code, name, dimension) VALUES (?,?,?,?)",
                  [("u-kg", "KG", "Kilogramo", "WEIGHT"), ("u-caja", "CAJA", "Caja", "PACKAGE")])
    c.execute("CREATE TABLE product_unit_conversions (id TEXT PRIMARY KEY, product_id TEXT,"
              " from_unit_id TEXT, to_unit_id TEXT, factor TEXT, rounding_scale INTEGER,"
              " effective_from TEXT, effective_to TEXT, active INTEGER DEFAULT 1)")
    c.execute("INSERT INTO product_unit_conversions (id, product_id, from_unit_id, to_unit_id,"
              " factor) VALUES ('c1','p1','u-caja','u-kg','20')")
    c.execute("UPDATE products SET base_unit_id='u-kg' WHERE id='p1'")
    c.commit()
    yield c
    c.close()


@pytest.fixture
def presenter(conn):
    return build_direct_purchase_presenter(conn, Session())


def _create(presenter, line, operation_id=None):
    return presenter.create(
        supplier_id="sup-1", lines=[line], mode="DIRECT_WITH_IMMEDIATE_RECEIPT",
        payment_condition="SUPPLIER_CREDIT", branch_id="br-1", warehouse_id="wh-1",
        operation_id=operation_id)


def _line_row(conn):
    return conn.execute("SELECT purchase_unit, inventory_unit, conversion_factor"
                        " FROM direct_purchase_lines").fetchone()


# ── el caso de uso toma las unidades de Productos ──────────────────────────────

def test_profile_comes_from_the_product_master(presenter):
    profile = presenter.purchase_profile("p1")
    assert profile.base_unit == "KG"
    assert {u.code: u.factor_to_base for u in profile.units} == {
        "KG": Decimal("1"), "CAJA": Decimal("20")}


def test_line_without_unit_is_bought_in_the_base_unit(conn, presenter):
    ok, msg, _ = _create(presenter, CartLineVM("p1", "Pollo", Decimal("3"), Decimal("50")))
    assert ok, msg
    unit, inventory_unit, factor = _line_row(conn)
    assert (unit, inventory_unit, Decimal(factor)) == ("KG", "KG", Decimal("1"))


def test_factor_sent_by_the_screen_is_ignored(conn, presenter):
    line = CartLineVM("p1", "Pollo", Decimal("2"), Decimal("400"), purchase_unit="CAJA",
                      inventory_unit="PZA", conversion_factor=Decimal("5"))
    ok, msg, _ = _create(presenter, line)
    assert ok, msg
    unit, inventory_unit, factor = _line_row(conn)
    assert (unit, inventory_unit, Decimal(factor)) == ("CAJA", "KG", Decimal("20"))


def test_unconfigured_presentation_is_rejected_with_a_readable_message(conn, presenter):
    line = CartLineVM("p1", "Pollo", Decimal("2"), Decimal("400"), purchase_unit="BULTO")
    ok, msg, data = _create(presenter, line)
    assert not ok and data["error_code"] == "UNIT_NOT_CONFIGURED"
    assert "BULTO" in msg and "Productos" in msg
    assert conn.execute("SELECT COUNT(*) FROM direct_purchases").fetchone()[0] == 0


def test_receipt_event_carries_cost_per_inventory_unit(conn, presenter):
    line = CartLineVM("p1", "Pollo", Decimal("2"), Decimal("400"), purchase_unit="CAJA")
    ok, msg, data = _create(presenter, line)
    assert ok, msg
    ok, msg, _ = presenter.confirm(data["entity_id"], None)
    assert ok, msg
    payload = json.loads(conn.execute(
        "SELECT payload_json FROM procurement_outbox WHERE event_name='DIRECT_PURCHASE_RECEIVED'"
    ).fetchone()[0])
    (inventory_line,) = payload["inventory_lines"]
    assert Decimal(inventory_line["quantity"]) == Decimal("40")
    assert Decimal(inventory_line["unit_cost"]) == Decimal("20")
    assert inventory_line["inventory_unit"] == "KG"


# ── el diálogo sólo ELIGE entre presentaciones configuradas ────────────────────

def _dialog(app, presenter):
    dialog = dialogs.AddCartLineDialog(
        None, product_provider=lambda q: presenter.product_options(q, "br-1"),
        profile_provider=presenter.purchase_profile)
    dialog._product.set_selected_label("p1", "Pollo")
    dialog._product_changed()
    return dialog


def test_dialog_has_no_manual_weight_or_conversion_fields(app, presenter):
    dialog = _dialog(app, presenter)
    assert not dialog.findChildren(QCheckBox)
    labels = " ".join(label.text() for label in dialog.findChildren(QLabel))
    assert "Factor de conversión" not in labels and "por peso" not in labels
    assert not hasattr(dialog, "_conversion") and not hasattr(dialog, "_is_weight")


def test_dialog_offers_only_configured_units_and_derives_the_line(app, presenter):
    dialog = _dialog(app, presenter)
    offered = {dialog._unit.itemData(i) for i in range(dialog._unit.count())} - {None}
    assert offered == {"KG", "CAJA"}
    assert dialog._unit.current_id() == "KG"          # base preseleccionada
    dialog._unit.set_current_id("CAJA")
    dialog._quantity.set_decimal("2")
    dialog._unit_cost.set_decimal("400")
    assert "1 Caja = 20 KG" in dialog._conversion_hint.text()
    assert "40 KG" in dialog._conversion_hint.text()
    assert dialog._cost_label.text() == "Costo por caja"
    line = dialog.line()
    assert (line.purchase_unit, line.inventory_unit, line.conversion_factor) == (
        "CAJA", "KG", Decimal("20"))


def test_weight_unit_captures_three_decimals(app, presenter):
    dialog = _dialog(app, presenter)
    dialog._quantity.setText("1.255")
    assert dialog._quantity.decimal_value() == Decimal("1.255")


# ── la compra rápida se VE guardar y confirmar ─────────────────────────────────

@pytest.fixture
def page(app, presenter):
    widget = DirectPurchaseCreatePage(presenter)
    widget.resize(1366, 768)
    widget.show()
    app.processEvents()
    yield widget
    widget.close()


def test_confirming_clears_the_table_and_shows_the_folio(conn, page):
    page._supplier_selected("sup-1")
    page._payment.set_current_id("SUPPLIER_CREDIT")
    page._warehouse.set_current_id("wh-1")
    page._cart = [CartLineVM("p1", "Pollo", Decimal("3"), Decimal("50"))]
    page._render()
    page._confirm_purchase()
    assert conn.execute("SELECT status FROM direct_purchases").fetchone()[0] == "RECEIVED"
    assert page._table.rowCount() == 0                      # antes quedaba pintada
    assert page._notice.property("state") == "success"
    assert "CD-2026-000001 confirmada" in page._notice.text()
    assert page._add.isEnabled() and page._cancel.text() == "Cancelar captura"


def test_mode_and_condition_show_what_will_be_saved(page):
    # §11: tipo y surtido son combos separados; juntos dan el modo que se guarda.
    assert page._kind.current_id() == "GOODS"
    assert page._fulfillment.current_id() == "IMMEDIATE_RECEIPT"
    assert page._mode() == "DIRECT_WITH_IMMEDIATE_RECEIPT"
    assert page._payment.current_id() == "IMMEDIATE_PAYMENT"


def test_validation_error_is_a_prominent_banner(page):
    page._save_draft()
    assert page._notice.property("role") == "banner"
    assert page._notice.property("state") == "error"
    assert page._notice.text().startswith("No se puede guardar todavía")


# ── compras GLOBALES: la sucursal del formulario sólo MARCA (2026-09-25) ──────

def test_search_is_global_and_marks_products_disabled_in_the_form_branch(conn, presenter):
    conn.execute("CREATE TABLE branch_product (id TEXT, product_id TEXT, branch_id TEXT,"
                 " enabled INTEGER, notes TEXT, created_at TEXT)")
    conn.execute("INSERT INTO branch_product VALUES ('bp1','p1','br-9',1,NULL,NULL)")
    conn.commit()
    (en_br9,) = presenter.product_options("Pollo", "br-9")
    assert en_br9.id == "p1" and "deshabilitado" not in en_br9.subtitle
    assert en_br9.tooltip == ""
    (en_br1,) = presenter.product_options("Pollo", "br-1")      # sigue apareciendo
    assert en_br1.subtitle == "P1 · deshabilitado para esta sucursal"
    assert en_br1.tooltip == "Habilítalo en Productos → Sucursales y surtidos."
    # y se puede comprar igual: el caso de uso no exige habilitación
    ok, msg, _ = _create(presenter, CartLineVM("p1", "Pollo", Decimal("1"), Decimal("10")))
    assert ok, msg


def test_empty_search_never_blames_branch_enablement(presenter):
    reason = presenter.product_search_reason("tornillo", "br-1") or ""
    assert "habilit" not in reason.lower()


def test_disabled_mark_is_a_tooltip_on_the_result_row(app, conn, presenter):
    from PyQt5.QtCore import Qt
    from frontend.desktop.components import EntitySearchInput
    conn.execute("CREATE TABLE branch_product (id TEXT, product_id TEXT, branch_id TEXT,"
                 " enabled INTEGER, notes TEXT, created_at TEXT)")
    conn.commit()
    box = EntitySearchInput(provider=lambda q: presenter.product_options(q, "br-1"))
    box._run_search("Pollo")
    item = box._results.item(0)
    assert item.text() == "Pollo — P1 · deshabilitado para esta sucursal"
    assert item.toolTip() == "Habilítalo en Productos → Sucursales y surtidos."
    assert item.flags() & Qt.ItemIsEnabled          # seleccionable
