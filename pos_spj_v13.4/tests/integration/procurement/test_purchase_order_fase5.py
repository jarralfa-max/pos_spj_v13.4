"""FASE 5 Compras (2026-09-25): solicitud → orden de compra.

Defectos que estas pruebas fijan:
* En producción NO se podía crear ninguna orden: ambas entradas exigían
  `default_warehouse()` y la sesión real (`LegacySessionAdapter`) nunca trae
  almacén. Aquí la sesión imita eso (`active_warehouse_id=""`).
* La orden no validaba nada contra el maestro (producto activo, almacén de la
  sucursal, unidad) y el factor se tecleaba.
* Una línea inválida consumía el folio OC (hueco en la secuencia).
* La recepción mandaba a inventario la cantidad en unidad de COMPRA y sin costo.
* Un rechazo del backend cerraba el diálogo y se perdía la captura; cada intento
  llevaba un `operation_id` nuevo (doble clic = dos órdenes).
"""

import json
import os
import sqlite3
from decimal import Decimal
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt5.QtWidgets", exc_type=ImportError)

from PyQt5.QtWidgets import QApplication  # noqa: E402

from backend.application.procurement.permissions import ALL_PURCHASE_PERMISSIONS  # noqa: E402
from backend.infrastructure.db.schema.document_output_schema import (  # noqa: E402
    create_document_numbering_schema,
)
from backend.infrastructure.db.schema.procurement_schema import (  # noqa: E402
    create_procurement_schema,
)
from frontend.desktop.modules.purchasing.dialogs import enterprise_dialogs  # noqa: E402
from frontend.desktop.modules.purchasing.enterprise_routes import (  # noqa: E402
    build_enterprise_presenter,
)
from frontend.desktop.modules.purchasing.pages import enterprise_pages  # noqa: E402
from tests.integration._supplier_cutover import apply_supplier_cutover  # noqa: E402
from tests.integration.procurement._purchase_context import seed_purchase_context  # noqa: E402


class RealShapedSession:
    """Como el adaptador REAL: sucursal activa, almacén SIEMPRE vacío."""

    is_active = True
    user_id = "user-1"
    active_branch_id = "br-1"
    active_warehouse_id = ""

    def tiene_permiso(self, code):
        return code in ALL_PURCHASE_PERMISSIONS


class Approver(RealShapedSession):
    user_id = "user-2"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    create_procurement_schema(c)
    create_document_numbering_schema(c)
    c.execute("CREATE TABLE proveedores(id TEXT PRIMARY KEY, nombre TEXT, activo INTEGER)")
    c.execute("INSERT INTO proveedores VALUES ('s1','Proveedor Uno',1)")
    apply_supplier_cutover(c)
    seed_purchase_context(c)      # p1/p2 activos; wh-1 de br-1
    c.execute("INSERT INTO warehouses (id, code, name, branch_id) VALUES"
              " ('wh-9','AL9','Almacén Otra','br-9')")
    c.execute("CREATE TABLE sucursales(id TEXT PRIMARY KEY, nombre TEXT, activa INTEGER)")
    c.execute("INSERT INTO sucursales VALUES ('br-1','Sucursal Centro',1)")
    c.execute("CREATE TABLE usuarios_sucursales (usuario_id TEXT, sucursal_id TEXT)")
    c.execute("INSERT INTO usuarios_sucursales VALUES ('user-1','br-1')")
    # Productos: p1 en KG con presentación CAJA = 20 KG.
    c.execute("CREATE TABLE units_of_measure (id TEXT PRIMARY KEY, code TEXT, name TEXT,"
              " dimension TEXT, active INTEGER DEFAULT 1)")
    c.executemany("INSERT INTO units_of_measure (id, code, name, dimension) VALUES (?,?,?,?)",
                  [("u-kg", "KG", "Kilogramo", "WEIGHT"), ("u-caja", "CAJA", "Caja", "PACKAGE")])
    c.execute("CREATE TABLE product_unit_conversions (id TEXT PRIMARY KEY, product_id TEXT,"
              " from_unit_id TEXT, to_unit_id TEXT, factor TEXT, rounding_scale INTEGER,"
              " effective_from TEXT, effective_to TEXT, active INTEGER DEFAULT 1)")
    c.execute("INSERT INTO product_unit_conversions (id, product_id, from_unit_id,"
              " to_unit_id, factor) VALUES ('c1','p1','u-caja','u-kg','20')")
    c.execute("UPDATE products SET base_unit_id='u-kg' WHERE id='p1'")
    c.commit()
    yield c
    c.close()


@pytest.fixture
def presenter(conn):
    return build_enterprise_presenter(conn, RealShapedSession())


def _order(presenter, *, warehouse="wh-1", lines=None, operation_id=None):
    return presenter.create_order(
        operation_id=operation_id, supplier_id="s1", branch_id="br-1",
        warehouse_id=warehouse,
        lines=lines or [{"product_id": "p1", "quantity": "2", "unit_price": "400",
                         "purchase_unit": "CAJA"}])


def _count(conn):
    return conn.execute("SELECT COUNT(*) FROM purchase_orders").fetchone()[0]


# ── el caso de uso aplica las reglas del maestro ─────────────────────────────

def test_factor_comes_from_products_not_from_the_screen(conn, presenter):
    ok, msg, _ = _order(presenter, lines=[{
        "product_id": "p1", "quantity": "2", "unit_price": "400",
        "purchase_unit": "CAJA", "conversion_factor": "5"}])
    assert ok, msg
    row = conn.execute("SELECT purchase_unit, inventory_unit, conversion_factor"
                       " FROM purchase_order_lines").fetchone()
    assert (row[0], row[1], Decimal(row[2])) == ("CAJA", "KG", Decimal("20"))


def test_warehouse_of_another_branch_is_rejected(conn, presenter):
    ok, _msg, data = _order(presenter, warehouse="wh-9")
    assert not ok and data["error_code"] == "WAREHOUSE_NOT_IN_BRANCH"
    assert _count(conn) == 0


def test_unknown_product_and_unconfigured_unit_are_rejected(conn, presenter):
    ok, _m, data = _order(presenter, lines=[{"product_id": "nope", "quantity": "1",
                                              "unit_price": "10"}])
    assert not ok and data["error_code"] == "PRODUCT_NOT_ACTIVE"
    ok, msg, data = _order(presenter, lines=[{"product_id": "p1", "quantity": "1",
                                               "unit_price": "10", "purchase_unit": "BULTO"}])
    assert not ok and data["error_code"] == "UNIT_NOT_CONFIGURED" and "Productos" in msg


def test_a_rejected_order_does_not_burn_a_folio(conn, presenter):
    ok, _m, _ = _order(presenter, lines=[{"product_id": "p1", "quantity": "1",
                                           "unit_price": "0"}])
    assert not ok
    ok, _m, data = _order(presenter)
    assert ok and data["document_number"].endswith("-000001")


def test_same_operation_id_returns_the_same_order(conn, presenter):
    ok1, _m, d1 = _order(presenter, operation_id="op-fixed")
    ok2, _m, d2 = _order(presenter, operation_id="op-fixed")
    assert ok1 and ok2 and d1["entity_id"] == d2["entity_id"] and _count(conn) == 1


# ── recepción: cantidad convertida y costo por unidad de inventario ───────────

def test_receipt_sends_inventory_quantity_and_cost(conn, presenter):
    ok, msg, data = _order(presenter)
    assert ok, msg
    approver = build_enterprise_presenter(conn, Approver())
    assert approver.approve_order(data["entity_id"])[0]
    assert approver.send_order(data["entity_id"])[0]
    ok, msg, _ = approver.receive_order(data["entity_id"], receipt_lines=[
        {"product_id": "p1", "received_quantity": "2", "accepted_quantity": "2"}])
    assert ok, msg
    payload = json.loads(conn.execute(
        "SELECT payload_json FROM procurement_outbox WHERE event_name='GOODS_RECEIPT_COMPLETED'"
    ).fetchone()[0])
    (line,) = payload["inventory_lines"]
    assert Decimal(line["quantity"]) == Decimal("40")       # 2 cajas × 20 kg
    assert Decimal(line["unit_cost"]) == Decimal("20")      # $400 / 20 kg
    assert line["inventory_unit"] == "KG"


# ── pantalla: se puede crear una orden con la sesión REAL ─────────────────────

def _approved_requisition(conn, presenter, *, estimated=None):
    line = {"product_id": "p1", "quantity": "3"}
    if estimated:
        line["estimated_unit_cost"] = estimated
    ok, msg, data = presenter.create_requisition(
        branch_id="br-1", purchase_type="INVENTORY", priority="NORMAL",
        business_reason="reabasto", lines=[line])
    assert ok, msg
    assert presenter.submit_requisition(data["entity_id"])[0]
    assert build_enterprise_presenter(conn, Approver()).approve_requisition(
        data["entity_id"], approve=True)[0]
    return presenter.requisition_detail(data["entity_id"])


def _drive(monkeypatch, fill):
    """Sustituye `exec_` por: llenar, aceptar (reintentando si se pide) y
    devolver el resultado. Guarda el diálogo para inspeccionarlo."""
    seen = {}

    def fake_exec(self):
        seen["dialog"] = self
        fill(self)
        return self.result()

    monkeypatch.setattr(enterprise_dialogs.OrderFormDialog, "exec_", fake_exec)
    return seen


def _pick_supplier(dialog):
    dialog._supplier.set_selected_label("s1", "Proveedor Uno")


def test_order_from_requisition_works_without_a_session_warehouse(
        app, conn, presenter, monkeypatch):
    detail = _approved_requisition(conn, presenter)

    def fill(dialog):
        _pick_supplier(dialog)
        assert dialog._warehouse.current_id() == "wh-1"   # único: preseleccionado
        # la solicitud no traía costo: la línea NO trae 0, pide el precio
        assert dialog._lines._display_rows()[0][3] == "Falta precio"
        dialog.accept()
        assert "Captura el precio de: Pollo" in dialog.error_text()
        dialog._lines._lines[0]["unit_price"] = "55"
        dialog.accept()

    seen = _drive(monkeypatch, fill)
    result = enterprise_pages.open_order_form(None, presenter, source_requisition=detail)
    assert result is not None and result[0] and "OC-" in result[1]
    assert seen["dialog"]._lines._display_rows()[0][0] == "Pollo"   # nombre, no id
    row = conn.execute("SELECT source_requisition_id, warehouse_id FROM purchase_orders"
                       ).fetchone()
    assert row == (detail.id, "wh-1")
    assert conn.execute("SELECT unit_price FROM purchase_order_lines").fetchone()[0] == "55"


def test_backend_rejection_keeps_the_dialog_open_with_the_capture(
        app, conn, presenter, monkeypatch):
    conn.execute("UPDATE products SET lifecycle_status='INACTIVE' WHERE id='p1'")
    conn.commit()

    def fill(dialog):
        _pick_supplier(dialog)
        dialog._lines.set_lines([{"product_id": "p1", "product_label": "Pollo",
                                  "quantity": "1", "purchase_nature": "INVENTORY",
                                  "unit_price": "10"}])
        dialog.accept()

    seen = _drive(monkeypatch, fill)
    assert enterprise_pages.open_order_form(None, presenter) is None
    dialog = seen["dialog"]
    assert dialog.result() == 0 and "no está activo" in dialog.error_text()
    assert dialog._lines.lines()                    # la captura sigue ahí
    assert _count(conn) == 0


def test_double_submit_of_the_same_capture_creates_one_order(
        app, conn, presenter, monkeypatch):
    def fill(dialog):
        _pick_supplier(dialog)
        dialog._lines.set_lines([{"product_id": "p1", "product_label": "Pollo",
                                  "quantity": "1", "purchase_nature": "INVENTORY",
                                  "unit_price": "10"}])
        dialog._on_submit(dialog.values(), dialog.operation_id)   # primer clic
        dialog.accept()                                           # segundo clic

    _drive(monkeypatch, fill)
    assert enterprise_pages.open_order_form(None, presenter) is not None
    assert _count(conn) == 1


def test_branch_change_reloads_warehouses(app, presenter):
    dialog = enterprise_dialogs.OrderFormDialog(
        branch_options=[("br-1", "Centro"), ("br-9", "Otra")], branch_id="br-1",
        warehouse_provider=presenter.warehouse_options,
        preselect_warehouse=presenter.preselected_warehouse)
    assert dialog._warehouse.current_id() == "wh-1"
    dialog._branch.set_current_id("br-9")
    assert dialog._warehouse.current_id() == "wh-9"
    assert dialog._warehouse.findData("wh-1") < 0


# ── migración 277: tablas creadas antes de las columnas nuevas ────────────────

def test_old_purchase_order_lines_table_gets_the_unit_columns():
    c = sqlite3.connect(":memory:")
    create_procurement_schema(c)
    c.execute("ALTER TABLE purchase_order_lines RENAME TO pol_new")
    c.execute("CREATE TABLE purchase_order_lines (id TEXT PRIMARY KEY,"
              " purchase_order_id TEXT, product_id TEXT, conversion_factor TEXT)")
    create_procurement_schema(c)
    cols = {r[1] for r in c.execute("PRAGMA table_info(purchase_order_lines)")}
    assert {"purchase_unit", "inventory_unit"} <= cols


# ── la pantalla muestra NOMBRES de producto, nunca ids ────────────────────────

def test_requisition_order_and_invoice_details_carry_product_names(conn, presenter):
    detail = _approved_requisition(conn, presenter)
    assert detail.lines[0].product_name == "P1 · Pollo"
    ok, msg, data = _order(presenter)
    assert ok, msg
    order = presenter.order_detail(data["entity_id"])
    assert order.lines[0].product_name == "P1 · Pollo" and order.lines[0].purchase_unit == "CAJA"
    assert presenter.product_label("nope") == "Producto"
