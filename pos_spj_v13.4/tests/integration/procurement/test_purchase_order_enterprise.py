"""FASE 7 Compras (2026-09-25): orden de compra completa + confirmación del proveedor.

§23: encabezado (fecha requerida/prometida, condición de pago, forma y dirección de
entrega, moneda y tipo de cambio, centro de costo, proyecto, contrato, notas) y
líneas con descuento, impuesto, subtotal y cantidad en unidad de compra y de
inventario.

§24: «Enviada» NO es «aceptada». Antes `send_order(acknowledge=True)` marcaba la
orden como confirmada sin un solo dato del proveedor. Ahora la confirmación se
registra aparte, con referencia, fecha de entrega confirmada, cantidades por línea,
comentarios y EXCEPCIONES calculadas contra lo pedido.
"""

import json
import os
import sqlite3
from datetime import date, timedelta
from decimal import Decimal

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt5.QtWidgets", exc_type=ImportError)

from PyQt5.QtWidgets import QApplication  # noqa: E402

from backend.application.procurement.permissions import (  # noqa: E402
    ALL_PURCHASE_PERMISSIONS,
    PurchasePermissions,
)
from backend.infrastructure.db.schema.document_output_schema import (  # noqa: E402
    create_document_numbering_schema,
)
from backend.infrastructure.db.schema.procurement_schema import (  # noqa: E402
    create_procurement_schema,
)
from frontend.desktop.modules.purchasing.dialogs import enterprise_dialogs  # noqa: E402
from frontend.desktop.modules.purchasing.document_detail import OrderDetailPanel  # noqa: E402
from frontend.desktop.modules.purchasing.enterprise_routes import (  # noqa: E402
    build_enterprise_presenter,
)
from frontend.desktop.modules.purchasing.pages import enterprise_pages  # noqa: E402
from tests.integration._supplier_cutover import apply_supplier_cutover  # noqa: E402
from tests.integration.procurement._purchase_context import seed_purchase_context  # noqa: E402


class Buyer:
    is_active = True
    user_id = "user-1"
    active_branch_id = "br-1"
    active_warehouse_id = ""

    def tiene_permiso(self, code):
        return code in ALL_PURCHASE_PERMISSIONS


class Approver(Buyer):
    user_id = "user-2"


class NoAcknowledge(Buyer):
    def tiene_permiso(self, code):
        return code in ALL_PURCHASE_PERMISSIONS and code != PurchasePermissions.ORDER_ACKNOWLEDGE


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    create_procurement_schema(c)
    create_document_numbering_schema(c)
    c.execute("CREATE TABLE proveedores(id TEXT PRIMARY KEY, nombre TEXT, activo INTEGER)")
    c.execute("INSERT INTO proveedores VALUES ('s1','Avícola Norte',1)")
    apply_supplier_cutover(c)
    seed_purchase_context(c)
    c.execute("CREATE TABLE sucursales(id TEXT PRIMARY KEY, nombre TEXT, activa INTEGER)")
    c.execute("INSERT INTO sucursales VALUES ('br-1','Centro',1)")
    c.execute("CREATE TABLE usuarios(id TEXT PRIMARY KEY, nombre TEXT, sucursal_id TEXT)")
    c.execute("INSERT INTO usuarios VALUES ('user-1','Ana Compras','br-1')")
    c.execute("CREATE TABLE usuarios_sucursales (usuario_id TEXT, sucursal_id TEXT)")
    c.execute("INSERT INTO usuarios_sucursales VALUES ('user-1','br-1')")
    # FASE 8: la recolección en proveedor exige una de SUS bodegas.
    c.execute("INSERT INTO supplier_addresses (id, supplier_id, address_type, line, city,"
              " state, label) VALUES ('addr-1','s1','WAREHOUSE','Carretera 57 km 3',"
              " 'San Juan del Río','Querétaro','Bodega Norte')")
    c.commit()
    yield c
    c.close()


@pytest.fixture
def buyer(conn):
    return build_enterprise_presenter(conn, Buyer())


REQUIRED = (date.today() + timedelta(days=5)).isoformat()


def _order(buyer, **extra):
    fields = dict(supplier_id="s1", branch_id="br-1", warehouse_id="wh-1",
                  lines=[{"product_id": "p1", "quantity": "10", "unit_price": "100",
                          "discount": "50", "tax": "16"},
                         {"product_id": "p2", "quantity": "4", "unit_price": "25"}],
                  required_date=REQUIRED, payment_terms="NET_30",
                  delivery_method="SUPPLIER_PICKUP", origin_supplier_address_id="addr-1",
                  cost_center="CC-COCINA",
                  project_reference="Temporada", contract_reference="CT-7",
                  notes="Entregar temprano")
    fields.update(extra)
    ok, msg, data = buyer.create_order(**fields)
    assert ok, msg
    return data["entity_id"]


def _sent(conn, buyer, **extra):
    order_id = _order(buyer, **extra)
    approver = build_enterprise_presenter(conn, Approver())
    assert approver.approve_order(order_id)[0]
    assert approver.send_order(order_id)[0]
    return order_id


# ── §23 orden completa ────────────────────────────────────────────────────────

def test_header_and_line_amounts_are_persisted_and_read_back(buyer):
    detail = buyer.order_detail(_order(buyer))
    assert (detail.required_date, detail.payment_terms, detail.delivery_method) == (
        REQUIRED, "NET_30", "SUPPLIER_PICKUP")
    assert (detail.cost_center, detail.project_reference, detail.contract_reference,
            detail.notes) == ("CC-COCINA", "Temporada", "CT-7", "Entregar temprano")
    assert (detail.branch_name, detail.warehouse_name, detail.buyer_name) == (
        "Centro", "Almacén", "Ana Compras")
    first = next(ln for ln in detail.lines if ln.product_id == "p1")
    assert (first.discount, first.tax, Decimal(first.subtotal)) == ("50", "16", Decimal("950"))
    assert first.inventory_quantity == "10" and first.inventory_unit == "PZA"
    # total = (1000 - 50 + 16) + 100
    assert Decimal(detail.total) == Decimal("1066")


def test_foreign_currency_requires_an_exchange_rate(buyer):
    ok, msg, _ = buyer.create_order(supplier_id="s1", branch_id="br-1", warehouse_id="wh-1",
                                    currency_code="USD",
                                    lines=[{"product_id": "p1", "quantity": "1",
                                            "unit_price": "10"}])
    assert not ok and "tipo de cambio" in msg
    detail = buyer.order_detail(_order(buyer, currency_code="USD", exchange_rate="17.25"))
    assert (detail.currency_code, detail.exchange_rate) == ("USD", "17.25")


def test_discount_larger_than_the_line_is_refused(buyer):
    ok, msg, _ = buyer.create_order(supplier_id="s1", branch_id="br-1", warehouse_id="wh-1",
                                    lines=[{"product_id": "p1", "quantity": "1",
                                            "unit_price": "10", "discount": "11"}])
    assert not ok and "descuento" in msg.lower()


def test_unknown_delivery_method_is_refused(buyer):
    ok, msg, _ = buyer.create_order(supplier_id="s1", branch_id="br-1", warehouse_id="wh-1",
                                    delivery_method="TELEPORT",
                                    lines=[{"product_id": "p1", "quantity": "1",
                                            "unit_price": "10"}])
    assert not ok and "entrega" in msg.lower()


# ── §24 confirmación del proveedor ────────────────────────────────────────────

def test_sending_is_not_accepting(app, conn, buyer):
    order_id = _sent(conn, buyer)
    detail = buyer.order_detail(order_id)
    assert detail.status == "SENT" and detail.confirmed_at is None
    panel = OrderDetailPanel(None, buyer.capabilities())
    panel.load_detail(detail)
    assert "sin confirmación del proveedor" in panel._summary.text()
    assert panel.acknowledge_button.isEnabled()
    assert "SENT" not in panel._summary.text()          # estado en español


def test_confirmation_records_supplier_data_and_exceptions(conn, buyer):
    order_id = _sent(conn, buyer)
    detail = buyer.order_detail(order_id)
    p1 = next(ln.id for ln in detail.lines if ln.product_id == "p1")
    late = (date.today() + timedelta(days=9)).isoformat()
    ok, msg, data = buyer.acknowledge_order(
        order_id, supplier_reference="PED-4471", confirmed_delivery_date=late,
        confirmed_quantities={p1: "8"}, comments="Sólo 8 disponibles")
    assert ok and msg == "Confirmación registrada con excepciones"
    assert data["exceptions"] == ["P1 · Pollo: confirma 8 de 10",
                                  f"Entrega prometida {late}, posterior a la requerida {REQUIRED}"]
    detail = buyer.order_detail(order_id)
    assert detail.status == "ACKNOWLEDGED" and detail.supplier_reference == "PED-4471"
    assert detail.confirmed_delivery_date == late and detail.promised_date == late
    assert detail.confirmation_comments == "Sólo 8 disponibles"
    assert {ln.product_id: ln.confirmed_quantity for ln in detail.lines} == {"p1": "8", "p2": "4"}
    payload = json.loads(conn.execute(
        "SELECT payload_json FROM procurement_outbox WHERE event_name="
        "'PURCHASE_ORDER_ACKNOWLEDGED'").fetchone()[0])
    assert payload["supplier_reference"] == "PED-4471" and len(payload["exceptions"]) == 2
    # y la orden confirmada se puede recibir
    approver = build_enterprise_presenter(conn, Approver())
    ok, msg, _ = approver.receive_order(order_id, receipt_lines=[
        {"product_id": "p1", "received_quantity": "8", "accepted_quantity": "8"}])
    assert ok, msg


def test_confirmation_without_differences_has_no_exceptions(conn, buyer):
    order_id = _sent(conn, buyer)
    ok, msg, data = buyer.acknowledge_order(order_id, supplier_reference="OK-1",
                                            confirmed_delivery_date=REQUIRED)
    assert ok and msg == "Confirmación registrada" and data["exceptions"] == []
    ok, msg, data = buyer.acknowledge_order(order_id, supplier_reference="OK-1")
    assert ok and data.get("already_registered")          # idempotente


def test_only_a_sent_order_can_be_confirmed_and_it_needs_the_permission(conn, buyer):
    draft = _order(buyer)
    ok, _msg, data = buyer.acknowledge_order(draft, supplier_reference="X")
    assert not ok and data["error_code"] == "VALIDATION"
    order_id = _sent(conn, buyer)
    restricted = build_enterprise_presenter(conn, NoAcknowledge())
    ok, _msg, data = restricted.acknowledge_order(order_id, supplier_reference="X")
    assert not ok and data["error_code"] == "PERMISSION_DENIED"
    assert not restricted.capabilities().order_acknowledge


# ── pantalla ──────────────────────────────────────────────────────────────────

def test_order_form_sends_the_enterprise_header(app, buyer):
    dialog = enterprise_dialogs.OrderFormDialog(
        branch_id="br-1", branch_options=[("br-1", "Centro")],
        warehouse_provider=buyer.warehouse_options,
        preselect_warehouse=buyer.preselected_warehouse,
        origin_provider=buyer.supplier_origin_options)
    dialog._payment_terms.set_current_id("NET_15")
    dialog._delivery_method.set_current_id("SUPPLIER_PICKUP")
    dialog._cost_center.setText("CC-1")
    assert not dialog._exchange_rate.isVisibleTo(dialog)
    dialog._currency.set_current_id("USD")
    assert dialog._exchange_rate.isVisibleTo(dialog)
    dialog._supplier.set_selected_label("s1", "Avícola Norte")
    dialog._reload_origins()
    assert dialog._origin.current_id() == "addr-1"      # única bodega: preseleccionada
    assert dialog._origin.currentText() == "Bodega Norte · San Juan del Río, Querétaro"
    dialog._lines.set_lines([{"product_id": "p1", "product_label": "Pollo", "quantity": "1",
                              "purchase_nature": "INVENTORY", "unit_price": "10"}])
    assert "tipo de cambio" in dialog.problem()
    dialog._exchange_rate.set_decimal("17.5")
    assert dialog.problem() is None
    values = dialog.values()
    assert (values["payment_terms"], values["delivery_method"], values["cost_center"],
            values["currency_code"], values["exchange_rate"]) == (
        "NET_15", "SUPPLIER_PICKUP", "CC-1", "USD", "17.5000")
    # Qt usa la hora local de Windows; conftest fuerza TZ=UTC sólo para Python.
    from PyQt5.QtCore import QDate
    assert values["required_date"] == QDate.currentDate().toString("yyyy-MM-dd")


def test_acknowledge_dialog_previews_exceptions_and_requires_a_reference(
        app, conn, buyer, monkeypatch):
    order_id = _sent(conn, buyer)
    seen = {}

    def fake_exec(self):
        self.accept()
        seen["missing_reference"] = self.error_text()
        self._quantities[0][2].set_decimal("7")
        seen["preview"] = self._exceptions.text()
        self._reference.setText("PED-1")
        self.accept()
        return self.result()

    monkeypatch.setattr(enterprise_dialogs.AcknowledgeOrderDialog, "exec_", fake_exec)
    ok, message = enterprise_pages.open_acknowledge_order(None, buyer, order_id)
    assert "referencia" in seen["missing_reference"]
    assert "confirma 7 de 10" in seen["preview"]
    assert ok and "confirma 7 de 10" in message
    assert buyer.order_detail(order_id).status == "ACKNOWLEDGED"


def test_old_purchase_orders_table_gets_the_new_columns():
    c = sqlite3.connect(":memory:")
    create_procurement_schema(c)
    for table in ("purchase_orders", "purchase_order_lines"):
        c.execute(f"ALTER TABLE {table} RENAME TO {table}_new")
    c.execute("CREATE TABLE purchase_orders (id TEXT PRIMARY KEY, supplier_id TEXT,"
              " source_award_id TEXT, payment_terms TEXT)")
    c.execute("CREATE TABLE purchase_order_lines (id TEXT PRIMARY KEY,"
              " purchase_order_id TEXT, conversion_factor TEXT)")
    create_procurement_schema(c)
    header = {r[1] for r in c.execute("PRAGMA table_info(purchase_orders)")}
    lines = {r[1] for r in c.execute("PRAGMA table_info(purchase_order_lines)")}
    assert {"required_date", "supplier_reference", "confirmation_exceptions",
            "exchange_rate", "cost_center"} <= header
    assert {"discount", "tax", "confirmed_quantity"} <= lines


def test_history_shows_spanish_actions_and_names_and_never_piles_up(app, conn, buyer):
    first = _sent(conn, buyer)
    second = _order(buyer)
    panel = OrderDetailPanel(None, buyer.capabilities())
    panel.load_detail(buyer.order_detail(first))
    panel.load_detail(buyer.order_detail(second))
    texts = [label.text() for label in panel._timeline._labels]
    assert len(texts) == 1 and "Orden creada · Ana Compras" in texts[0]
    panel.load_detail(buyer.order_detail(first))
    texts = " ".join(label.text() for label in panel._timeline._labels)
    assert "Orden enviada al proveedor" in texts
    assert "PURCHASE_ORDER" not in texts and "user-1" not in texts
