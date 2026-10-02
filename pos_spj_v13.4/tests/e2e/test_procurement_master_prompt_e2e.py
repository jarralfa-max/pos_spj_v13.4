"""Compras FASE 17 — las pruebas end-to-end obligatorias del §41.

La base NACE con el arranque real de la aplicación (`run_database_bootstrap_sequence`:
todas las migraciones, el mismo esquema que una instalación nueva), sin tablas
hechas a mano. Sobre ella se siembra lo mínimo que una instalación real tiene
(almacén, productos con sus presentaciones, proveedores, Finanzas) y cada prueba
recorre la cadena COMPLETA por la composición real de Compras, con el bus de
eventos real cableado en un bus LOCAL (el de la app es global):

    Compras → outbox → Inventario (existencias) → Precios (costo) → Finanzas (CxP)

1  Compra rápida: catálogo → proveedor → sucursal → almacén → guardar → consultar
   → confirmar → recibir → inventario → costo.
2  Cárnico de peso variable: 5 cajas, 127.850 kg reales a $95/kg.
3  Abarrote: 5 costales de 25 kg → 125 kg de inventario.
4  Solicitud sin precio → aprobar → OC → completar precio → guardar.
5  RFQ con 2 proveedores → adjudicación dividida → 2 órdenes.
6  Compra en origen: bodega del proveedor → embarque → contenedor → carga → sello
   → despacho → llegada → recepción → inventario.
7  Promedio móvil: 100 @ $40, salen 90, 10 @ $60 → $50.
8/9 Ninguna página muestra UUID ni estados técnicos.
10 Permisos: la pantalla y el backend niegan.
11 Crédito: orden → recepción → factura → conciliación → CxP → pago.
"""

from __future__ import annotations

import importlib
import shutil
import sqlite3
from datetime import date
from decimal import Decimal

import pytest

from backend.application.inventory.use_cases import PostInventoryMovementUseCase
from backend.application.logistics.authorization import LogisticsPermissions
from backend.application.procurement.integrations.procurement_outbox_dispatcher import (
    dispatch_procurement_outbox,
)
from backend.application.procurement.permissions import ALL_PURCHASE_PERMISSIONS
from backend.application.services.finance.finance_bootstrap import bootstrap_finance
from backend.bootstrap.run_database_bootstrap import run_database_bootstrap_sequence
from backend.shared.events.application_bus import ApplicationEventBus
from backend.shared.ids import new_uuid

pytest.importorskip("PyQt5.QtWidgets", exc_type=ImportError)

from PyQt5.QtWidgets import QApplication  # noqa: E402

from frontend.desktop.modules.purchasing.direct_purchase_routes import (  # noqa: E402
    build_direct_purchase_presenter,
)
from frontend.desktop.modules.purchasing.direct_purchase_view_models import (  # noqa: E402
    CartLineVM,
)
from frontend.desktop.modules.purchasing.enterprise_routes import (  # noqa: E402
    build_enterprise_presenter,
)

#: Sucursal que la instalación siembra (migraciones de aprovisionamiento).
BRANCH = "01900000-0000-7000-8000-000000000001"
WAREHOUSE = "wh-e2e"
_LOGISTICS = frozenset(v for k, v in vars(LogisticsPermissions).items()
                       if not k.startswith("_") and isinstance(v, str))
_263 = importlib.import_module("migrations.standalone.263_suppliers_legacy_into_master")


class Session:
    """Como la sesión real: sin almacén activo (el almacén es del documento)."""

    is_active = True
    active_branch_id = BRANCH
    active_warehouse_id = ""

    def __init__(self, user_id: str, permissions=None) -> None:
        self.user_id = user_id
        self._permissions = (ALL_PURCHASE_PERMISSIONS | _LOGISTICS
                             if permissions is None else frozenset(permissions))

    def tiene_permiso(self, code: str) -> bool:
        return code in self._permissions


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def template(tmp_path_factory):
    path = tmp_path_factory.mktemp("compras_e2e") / "template.db"
    result = run_database_bootstrap_sequence(path)
    assert result.success, result
    result.context.conn.close()
    return path


class Env:
    def __init__(self, conn) -> None:
        self.conn = conn
        self.bus = ApplicationEventBus()
        from backend.application.pricing.integrations.wiring import wire_pricing
        from backend.application.procurement.integrations.wiring import wire_procurement
        from backend.bootstrap.wiring.event_wiring import wire_procurement_downstream_bridges
        wire_procurement(self.bus, conn)
        wire_pricing(self.bus, conn)
        wire_procurement_downstream_bridges(self.bus, conn)

    def _dispatch(self) -> None:
        dispatch_procurement_outbox(self.conn, self.bus)

    def buyer(self, user="comprador", permissions=None):
        presenter = build_enterprise_presenter(self.conn, Session(user, permissions))
        presenter._dispatch = self._dispatch
        return presenter

    def approver(self):
        return self.buyer("gerente")

    def direct(self, user="comprador", permissions=None):
        presenter = build_direct_purchase_presenter(self.conn, Session(user, permissions))
        presenter._dispatch = self._dispatch
        return presenter

    # lecturas de otros contextos (sólo para verificar) ----------------------
    def stock(self, product_id) -> Decimal:
        value = self.conn.execute(
            "SELECT COALESCE(SUM(CAST(quantity AS NUMERIC)),0) FROM inventory_balances"
            " WHERE product_id=?", (product_id,)).fetchone()[0]
        return Decimal(str(value))

    def average_cost(self, product_id) -> Decimal:
        row = self.conn.execute("SELECT average_cost FROM product_cost WHERE product_id=?"
                                " AND branch_id=''", (product_id,)).fetchone()
        return Decimal(row[0]).quantize(Decimal("0.01")) if row else None


def _seed(conn) -> None:
    now = "2026-09-30T12:00:00+00:00"
    conn.execute("INSERT INTO warehouses (id, code, name, branch_id, warehouse_type,"
                 " created_at, updated_at) VALUES (?, 'ALM', 'Almacén general', ?, 'STORE',"
                 " ?, ?)", (WAREHOUSE, BRANCH, now, now))
    conn.execute("INSERT INTO units_of_measure (id, code, name, dimension, active, created_at)"
                 " VALUES (?, 'COSTAL', 'Costal', 'PACKAGE', 1, ?)", (new_uuid(), now))
    units = {row[1]: row[0] for row in conn.execute("SELECT id, code FROM units_of_measure")}

    def product(pid, code, name, *, catch_weight=0):
        conn.execute(
            "INSERT INTO products (id, code, name, name_normalized, product_type,"
            " lifecycle_status, base_unit_id, sellable, purchasable, inventory_managed,"
            " catch_weight_enabled, created_at) VALUES (?,?,?,?, 'PRIMARY_CUT', 'ACTIVE', ?,"
            " 1, 1, 1, ?, ?)", (pid, code, name, name.lower(), units["KG"], catch_weight, now))

    def conversion(pid, unit, factor):
        conn.execute("INSERT INTO product_unit_conversions (id, product_id, from_unit_id,"
                     " to_unit_id, factor, active) VALUES (?,?,?,?,?,1)",
                     (new_uuid(), pid, units[unit], units["KG"], factor))

    product("p-alas", "CAR-000001", "Alas")
    product("p-res", "CAR-RES-001", "Diezmillo de res", catch_weight=1)
    conversion("p-res", "CAJA", "25")
    conn.execute("INSERT INTO product_catch_weight_config (product_id, enabled,"
                 " nominal_unit_id, weight_unit_id, minimum_weight, maximum_weight,"
                 " price_basis) VALUES ('p-res', 1, ?, ?, '20', '30', 'PER_KILOGRAM')",
                 (units["CAJA"], units["KG"]))
    product("p-chile", "ABA-CHI-001", "Chile seco")
    conversion("p-chile", "COSTAL", "25")
    for sid, name in (("sup-1", "Carnes del Norte"), ("sup-2", "Abarrotes Querétaro")):
        conn.execute("INSERT INTO proveedores (id, nombre, activo) VALUES (?,?,1)", (sid, name))
    _263.run(conn)
    conn.execute("INSERT INTO supplier_addresses (id, supplier_id, address_type, line, city,"
                 " state, label) VALUES ('addr-1', 'sup-1', 'WAREHOUSE', 'Carretera 57 km 3',"
                 " 'San Juan del Río', 'Querétaro', 'Bodega Norte')")
    bootstrap_finance(conn)
    conn.commit()


@pytest.fixture
def env(template, tmp_path):
    path = tmp_path / "compras.db"
    shutil.copy(template, path)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")     # como el pool de la aplicación
    _seed(conn)
    yield Env(conn)
    conn.close()


def _direct_purchase(env, line: CartLineVM, *, mode="DIRECT_WITH_IMMEDIATE_RECEIPT",
                     payment="SUPPLIER_CREDIT", supplier="sup-1"):
    direct = env.direct()
    ok, msg, data = direct.create(supplier_id=supplier, lines=[line], mode=mode,
                                  payment_condition=payment, branch_id=BRANCH,
                                  warehouse_id=WAREHOUSE, operation_id=new_uuid())
    assert ok, msg
    return direct, data["entity_id"]


def _sent_order(env, lines, **header):
    buyer, approver = env.buyer(), env.approver()
    ok, msg, data = buyer.create_order(supplier_id=header.pop("supplier_id", "sup-1"),
                                       branch_id=BRANCH, warehouse_id=WAREHOUSE,
                                       lines=lines, **header)
    assert ok, msg
    order = data["entity_id"]
    assert approver.approve_order(order)[0]
    assert buyer.send_order(order)[0]
    return buyer, approver, order


# ── 1 ─────────────────────────────────────────────────────────────────────────
def test_1_quick_purchase_from_catalog_to_inventory_and_cost(env):
    direct = env.direct()
    (option,) = [o for o in direct.product_options("Alas", BRANCH)]
    assert option.id == "p-alas"
    direct, dp = _direct_purchase(env, CartLineVM(option.id, option.label, Decimal("100"),
                                                  Decimal("40")),
                                  mode="DIRECT_WITH_PENDING_RECEIPT")
    detail = direct.detail(dp)                                      # consultar
    assert (detail.status, detail.branch_name, detail.warehouse_name) == (
        "DRAFT", "Principal", "ALM · Almacén general")
    assert direct.confirm(dp, None)[0]
    assert env.stock("p-alas") == 0                                 # aún no se recibe
    ok, msg, _ = direct.receive(dp)
    assert ok, msg
    assert env.stock("p-alas") == Decimal("100")
    assert env.average_cost("p-alas") == Decimal("40.00")


# ── 2 ─────────────────────────────────────────────────────────────────────────
def test_2_variable_weight_meat_is_charged_and_stocked_by_real_weight(env, app):
    from frontend.desktop.modules.purchasing.dialogs.direct_purchase_dialogs import (
        AddCartLineDialog,
    )
    direct = env.direct()
    dialog = AddCartLineDialog(None, product_provider=lambda q: direct.product_options(q),
                               profile_provider=direct.purchase_profile)
    dialog._product.set_selected_label("p-res", "CAR-RES-001 · Diezmillo de res")
    dialog._product_changed()
    assert dialog._weight.isVisibleTo(dialog)                       # Productos lo pide
    dialog._unit.set_current_id("CAJA")
    dialog._quantity.set_decimal("5")
    dialog._unit_cost.set_decimal("95")
    assert "peso real" in dialog.validation_message()
    dialog._weight.set_decimal("127.850")
    line = dialog.line()
    assert line.line_subtotal() == Decimal("12145.75")              # 127.850 × 95

    direct, dp = _direct_purchase(env, line)
    assert direct.detail(dp).total == "12145.75"
    assert direct.confirm(dp, None)[0]
    assert env.stock("p-res") == Decimal("127.850")                 # peso real, no 5×25
    assert env.average_cost("p-res") == Decimal("95.00")            # $/kg
    receipt = env.conn.execute("SELECT net_weight FROM goods_receipt_lines").fetchone()
    assert Decimal(receipt[0]) == Decimal("127.850")


def test_2b_variable_weight_without_real_weight_is_rejected_by_the_backend(env):
    direct = env.direct()
    ok, msg, data = direct.create(
        supplier_id="sup-1", mode="DIRECT_WITH_IMMEDIATE_RECEIPT",
        payment_condition="SUPPLIER_CREDIT", branch_id=BRANCH, warehouse_id=WAREHOUSE,
        lines=[CartLineVM("p-res", "Diezmillo", Decimal("5"), Decimal("95"),
                          purchase_unit="CAJA")])
    assert not ok and data["error_code"] == "WEIGHT_REQUIRED"


# ── 3 ─────────────────────────────────────────────────────────────────────────
def test_3_grocery_sacks_enter_inventory_in_kilograms(env):
    profile = env.direct().purchase_profile("p-chile")
    assert {u.code for u in profile.units} == {"KG", "COSTAL"}
    direct, dp = _direct_purchase(env, CartLineVM("p-chile", "Chile seco", Decimal("5"),
                                                  Decimal("300"), purchase_unit="COSTAL"))
    assert direct.confirm(dp, None)[0]
    assert env.stock("p-chile") == Decimal("125")
    assert env.average_cost("p-chile") == Decimal("12.00")          # $300 / 25 kg


# ── 4 ─────────────────────────────────────────────────────────────────────────
def test_4_requisition_without_price_becomes_an_order(env):
    buyer, approver = env.buyer(), env.approver()
    ok, msg, data = buyer.create_requisition(
        branch_id=BRANCH, purchase_type="INVENTORY", priority="NORMAL",
        business_reason="reabasto", lines=[{"product_id": "p-alas", "quantity": "30"}])
    assert ok, msg
    rid = data["entity_id"]
    assert buyer.submit_requisition(rid)[0] and approver.approve_requisition(rid)[0]
    lines = [{"product_id": "p-alas", "quantity": "30"}]            # la PR no traía precio
    ok, msg, _ = buyer.create_order(supplier_id="sup-1", branch_id=BRANCH,
                                    warehouse_id=WAREHOUSE, requisition_id=rid,
                                    lines=lines)
    assert not ok and "precio" in msg.lower()
    lines[0]["unit_price"] = "41"                                   # completar precio
    ok, msg, data = buyer.create_order(supplier_id="sup-1", branch_id=BRANCH,
                                       warehouse_id=WAREHOUSE, requisition_id=rid,
                                       lines=lines)
    assert ok, msg
    assert env.conn.execute("SELECT status FROM purchase_requisitions WHERE id=?",
                            (rid,)).fetchone()[0] == "SOURCED"
    assert buyer.order_detail(data["entity_id"]).lines[0].unit_price == "41"


# ── 5 ─────────────────────────────────────────────────────────────────────────
def test_5_split_award_generates_one_order_per_supplier(env):
    buyer, approver = env.buyer(), env.approver()
    ok, msg, data = buyer.create_requisition(
        branch_id=BRANCH, purchase_type="INVENTORY", priority="HIGH", business_reason="rfq",
        lines=[{"product_id": "p-alas", "quantity": "10"},
               {"product_id": "p-chile", "quantity": "50"}])
    rid = data["entity_id"]
    assert buyer.submit_requisition(rid)[0] and approver.approve_requisition(rid)[0]
    ok, msg, data = buyer.create_rfq_from_requisition(rid, ["sup-1", "sup-2"])
    assert ok, msg
    rfq = data["entity_id"]
    for supplier, (alas, chile) in (("sup-1", ("40", "14")), ("sup-2", ("45", "12"))):
        assert buyer.capture_quote(rfq_id=rfq, supplier_id=supplier, lines=[
            {"product_id": "p-alas", "quantity": "10", "unit_price": alas},
            {"product_id": "p-chile", "quantity": "50", "unit_price": chile}])[0]
    best = {"p-alas": "sup-1", "p-chile": "sup-2"}
    ok, msg, _ = buyer.award_quote(award_lines=[
        {"quote_line_id": r.quote_line_id, "supplier_id": r.supplier_id,
         "awarded_quantity": r.quantity, "justification": "mejor precio"}
        for r in buyer.quote_comparison(rfq) if best[r.product_id] == r.supplier_id],
        reason="mejor precio")
    assert ok, msg
    award = buyer.award_orders(rfq)
    ok, msg, _ = buyer.generate_orders_from_award(award["award_id"], WAREHOUSE)
    assert ok, msg
    orders = dict(env.conn.execute(
        "SELECT o.supplier_id, l.unit_price FROM purchase_orders o"
        " JOIN purchase_order_lines l ON l.purchase_order_id=o.id").fetchall())
    assert orders == {"sup-1": "40", "sup-2": "12"}


# ── 6 ─────────────────────────────────────────────────────────────────────────
def test_6_origin_purchase_reaches_inventory(env):
    buyer, _, order = _sent_order(env, [{"product_id": "p-alas", "quantity": "20",
                                         "unit_price": "42"}],
                                  delivery_method="SUPPLIER_PICKUP",
                                  origin_supplier_address_id="addr-1")
    (document,) = buyer.origin_documents()
    assert document["origin_display"] == "Bodega Norte · San Juan del Río, Querétaro"
    ok, msg, detail = buyer.origin_create_shipment(document)
    assert ok, msg
    shipment = detail["id"]
    ok, msg, kind = buyer.origin_register_container_type(code="HUACAL", name="Huacal",
                                                         category="CRATE")
    assert ok, msg
    assert buyer.origin_register_container(code="HC-1", container_type_id=kind["id"])[0]
    ok, msg, detail = buyer.origin_attach_container(shipment, "HC-1")
    assert ok, msg
    (line,) = buyer.origin_loading_lines(shipment)
    ok, msg, detail = buyer.origin_assign_line(
        shipment, node_id=detail["nodes"][0]["id"], source_line_id=line["source_line_id"],
        quantity="20", net_weight="20.4", lot_number="L-1")
    assert ok, msg
    assert buyer.origin_seal_root(shipment, detail["nodes"][0]["id"], "S-1")[0]
    for step in (buyer.origin_dispatch, buyer.origin_mark_in_transit,
                 buyer.origin_register_arrival):
        ok, msg, _ = step(shipment)
        assert ok, msg
    (arrival,) = buyer.origin_arrival_lines(shipment)
    assert buyer.origin_record_count(shipment, content_id=arrival["content_id"],
                                     received_quantity="20", accepted_quantity="19",
                                     received_net_weight="20.4")[0]
    ok, msg, detail = buyer.origin_receive_and_close(shipment)
    assert ok, msg
    assert detail["status"] == "CLOSED"
    assert env.stock("p-alas") == Decimal("19")                     # sólo lo aceptado
    assert env.conn.execute("SELECT status FROM purchase_orders WHERE id=?",
                            (order,)).fetchone()[0] in ("RECEIVED", "PARTIALLY_RECEIVED")


# ── 7 ─────────────────────────────────────────────────────────────────────────
def test_7_moving_average_uses_real_stock(env):
    from backend.domain.inventory.entities.inventory_movement import (
        InventoryMovement, InventoryMovementLine,
    )
    from backend.domain.inventory.enums import MovementType
    direct, dp = _direct_purchase(env, CartLineVM("p-alas", "Alas", Decimal("100"),
                                                  Decimal("40")))
    assert direct.confirm(dp, None)[0]
    lot = env.conn.execute("SELECT lot_id FROM inventory_balances WHERE product_id='p-alas'"
                           " AND CAST(quantity AS NUMERIC)>0").fetchone()[0]
    location = env.conn.execute("SELECT location_id FROM inventory_balances"
                                " WHERE product_id='p-alas'").fetchone()[0]
    movement = InventoryMovement.create(
        movement_type=MovementType.ADJUSTMENT_OUT, branch_id=BRANCH,
        warehouse_id=WAREHOUSE, source_module="test", source_document_type="SALIDA",
        source_document_id="out-1", operation_id="out-1", created_by_user_id="u1",
        lines=[InventoryMovementLine.create(product_id="p-alas", quantity=Decimal("90"),
                                            from_location_id=location, lot_id=lot)])
    result = PostInventoryMovementUseCase().execute(env.conn, movement, actor_user_id="u1")
    assert result.success, result.message
    direct, dp = _direct_purchase(env, CartLineVM("p-alas", "Alas", Decimal("10"),
                                                  Decimal("60")))
    assert direct.confirm(dp, None)[0]
    assert env.stock("p-alas") == Decimal("20")
    assert env.average_cost("p-alas") == Decimal("50.00")


# ── 8 y 9 ─────────────────────────────────────────────────────────────────────
def test_8_9_no_uuid_nor_technical_status_on_screen(env, app):
    from PyQt5.QtWidgets import QTableWidget, QTabWidget

    from frontend.desktop.modules.purchasing.enterprise_routes import (
        create_enterprise_purchasing_view,
    )
    from frontend.desktop.modules.purchasing.navigation import (
        IMPLEMENTED_PURCHASING_ROUTES,
    )
    from tests.integration.procurement.test_no_technical_text_in_ui import (
        _problems,
        _visible_texts,
    )
    test_2_variable_weight_meat_is_charged_and_stocked_by_real_weight(env, app)
    test_4_requisition_without_price_becomes_an_order(env)

    class Container:
        db = env.conn
        session = Session("comprador")

    view = create_enterprise_purchasing_view(Container())
    view.resize(1366, 768)
    view.show()
    view.refresh_permissions()
    offenders = {}
    for route in IMPLEMENTED_PURCHASING_ROUTES:
        view.navigate_to(route.key)
        page = view.content.currentWidget()
        if hasattr(page, "ensure_loaded"):
            page.ensure_loaded()
        app.processEvents()
        texts = list(_visible_texts(page))
        for tabs in page.findChildren(QTabWidget):
            for index in range(tabs.count()):
                tabs.setCurrentIndex(index)
                app.processEvents()
                texts += _visible_texts(page)
        for table in page.findChildren(QTableWidget):
            for row in range(min(table.rowCount(), 4)):
                table.selectRow(row)
                app.processEvents()
                texts += _visible_texts(page)
        for text in texts:
            if _problems(text):
                offenders[f"{route.label}: {text[:80]}"] = _problems(text)
    view.close()
    assert not offenders, offenders


# ── 10 ────────────────────────────────────────────────────────────────────────
def test_10_permissions_are_denied_in_the_screen_and_in_the_backend(env):
    viewer = {"COMPRAS.ver", "COMPRAS.directa.ver", "COMPRAS.orden.ver"}
    direct = env.direct(permissions=viewer)
    assert not direct.capabilities().direct_create                  # la pantalla
    ok, msg, data = direct.create(
        supplier_id="sup-1", mode="DIRECT_WITH_IMMEDIATE_RECEIPT",
        payment_condition="SUPPLIER_CREDIT", branch_id=BRANCH, warehouse_id=WAREHOUSE,
        lines=[CartLineVM("p-alas", "Alas", Decimal("1"), Decimal("40"))])
    assert not ok and data["error_code"] == "PERMISSION_DENIED"     # el backend
    buyer = env.buyer(permissions=viewer)
    assert not buyer.capabilities().order_create
    ok, msg, data = buyer.create_order(supplier_id="sup-1", branch_id=BRANCH,
                                       warehouse_id=WAREHOUSE, lines=[
                                           {"product_id": "p-alas", "quantity": "1",
                                            "unit_price": "40"}])
    assert not ok and data.get("error_code") == "PERMISSION_DENIED"
    assert env.conn.execute("SELECT COUNT(*) FROM direct_purchases").fetchone()[0] == 0
    assert env.conn.execute("SELECT COUNT(*) FROM purchase_orders").fetchone()[0] == 0


# ── 11 ────────────────────────────────────────────────────────────────────────
def test_11_credit_purchase_ends_in_a_paid_payable(env):
    from backend.application.use_cases.finance.payable_use_cases import (
        AuthorizeSupplierPaymentUseCase,
        ExecuteSupplierPaymentUseCase,
        ScheduleSupplierPaymentUseCase,
    )
    buyer, approver, order = _sent_order(env, [{"product_id": "p-alas", "quantity": "50",
                                                "unit_price": "42", "discount": "100",
                                                "tax": "320"}])
    line = buyer.order_detail(order).lines[0].id
    assert buyer.receive_order(order, receipt_lines=[{
        "product_id": "p-alas", "purchase_order_line_id": line,
        "received_quantity": "50", "accepted_quantity": "50"}])[0]
    (expected,) = buyer.invoice_document_profile(order)["lines"]
    assert (expected["unit_price"], expected["tax"]) == ("40", "320.00")
    ok, msg, invoice = buyer.capture_invoice(
        supplier_id="sup-1", invoice_number="F-900", total="2320", purchase_order_id=order,
        lines=[{"product_id": "p-alas", "invoiced_quantity": "50", "unit_price": "40",
                "tax": "320", "purchase_order_line_id": line}])
    assert ok, msg
    ok, msg, data = approver.match_invoice(invoice["entity_id"])
    assert ok and data["match_result"] == "MATCHED", msg
    detail = buyer.invoice_detail(invoice["entity_id"])
    assert detail.payable["original_amount"] == "2320.00"
    bank = env.conn.execute("SELECT id FROM treasury_accounts WHERE account_type='BANK'"
                            ).fetchone()[0]
    payment = ScheduleSupplierPaymentUseCase().execute(
        env.conn, payable_id=env.conn.execute("SELECT id FROM payables").fetchone()[0],
        amount="2320.00", scheduled_date=date.today(), treasury_account_id=bank,
        scheduled_by="tesorero", operation_id=new_uuid())
    AuthorizeSupplierPaymentUseCase().execute(env.conn, payment_id=payment.id,
                                              authorized_by="director", operation_id=new_uuid())
    ExecuteSupplierPaymentUseCase().execute(env.conn, payment_id=payment.id,
                                            executed_date=date.today(), operation_id=new_uuid())
    assert buyer.invoice_detail(invoice["entity_id"]).payable["status"] == "SETTLED"
    debit, credit = env.conn.execute(
        "SELECT SUM(CAST(debit_amount AS NUMERIC)), SUM(CAST(credit_amount AS NUMERIC))"
        " FROM journal_lines").fetchone()
    assert debit == credit                                          # debe = haber
