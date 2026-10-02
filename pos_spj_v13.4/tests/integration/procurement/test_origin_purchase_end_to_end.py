"""FASE 8-11 Compras (2026-09-29): compra en origen de punta a punta.

Bodega del proveedor → OC con recolección → embarque (origen = bodega, no el
nombre del proveedor) → contenedor registrado → carga con lo que exige el producto
→ sello → despacho → tránsito → llegada → conteo/pesaje con rechazo → recepción
de la OC vinculada al embarque → inventario (sólo lo ACEPTADO, con lote y peso) →
embarque cerrado y contenedor libre.

Se arma con la composición REAL de Compras (`build_enterprise_presenter`), que
ahora construye Logística: antes nadie la construía en producción y «Compra en
origen» estaba apagada. La sesión imita la real (sin almacén activo).
"""

import importlib
import json
import sqlite3
from decimal import Decimal

import pytest

from backend.application.logistics.authorization import LogisticsPermissions
from backend.application.procurement.permissions import ALL_PURCHASE_PERMISSIONS
from backend.infrastructure.db.schema.document_output_schema import (
    create_document_numbering_schema,
)
from backend.infrastructure.db.schema.procurement_schema import create_procurement_schema
from frontend.desktop.modules.purchasing.enterprise_routes import build_enterprise_presenter
from tests.integration._supplier_cutover import apply_supplier_cutover
from tests.integration.procurement._purchase_context import seed_purchase_context

_LOGISTICS = frozenset(v for k, v in vars(LogisticsPermissions).items()
                       if not k.startswith("_") and isinstance(v, str))


class Buyer:
    is_active = True
    user_id = "user-1"
    active_branch_id = "br-1"
    active_warehouse_id = ""

    def tiene_permiso(self, code):
        return code in ALL_PURCHASE_PERMISSIONS or code in _LOGISTICS


class Approver(Buyer):
    user_id = "user-2"


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    create_procurement_schema(c)
    create_document_numbering_schema(c)
    c.execute("CREATE TABLE proveedores(id TEXT PRIMARY KEY, nombre TEXT, activo INTEGER)")
    c.execute("INSERT INTO proveedores VALUES ('s1','Avícola Norte',1)")
    apply_supplier_cutover(c)
    seed_purchase_context(c)
    # El maestro de Productos dice que el pollo exige lote y peso real.
    c.execute("ALTER TABLE products ADD COLUMN lot_controlled INTEGER DEFAULT 0")
    c.execute("ALTER TABLE products ADD COLUMN catch_weight_enabled INTEGER DEFAULT 0")
    c.execute("UPDATE products SET lot_controlled=1, catch_weight_enabled=1 WHERE id='p1'")
    c.execute("CREATE TABLE configuraciones (clave TEXT PRIMARY KEY, valor TEXT, tipo TEXT,"
              " grupo TEXT, descripcion TEXT)")
    for number in ("171_logistics_bounded_context_schema",
                   "172_logistics_loading_authorizations"):
        importlib.import_module(f"migrations.standalone.{number}").run(c)
    c.execute("INSERT INTO supplier_addresses (id, supplier_id, address_type, line, city,"
              " state, label) VALUES ('addr-n','s1','WAREHOUSE','Carretera 57 km 3',"
              " 'San Juan del Río','Querétaro','Bodega Norte')")
    c.commit()
    yield c
    c.close()


def _sent_order(conn, buyer):
    ok, msg, data = buyer.create_order(
        supplier_id="s1", branch_id="br-1", warehouse_id="wh-1",
        delivery_method="SUPPLIER_PICKUP", origin_supplier_address_id="addr-n",
        lines=[{"product_id": "p1", "quantity": "10", "unit_price": "50"}])
    assert ok, msg
    approver = build_enterprise_presenter(conn, Approver())
    assert approver.approve_order(data["entity_id"])[0]
    assert approver.send_order(data["entity_id"])[0]
    return data["entity_id"]


def test_origin_purchase_from_supplier_warehouse_to_inventory(conn):
    buyer = build_enterprise_presenter(conn, Buyer())
    order_id = _sent_order(conn, buyer)

    # FASE 8: la OC recuerda la bodega (id + foto) y el documento la muestra.
    snapshot = json.loads(conn.execute(
        "SELECT origin_address_snapshot FROM purchase_orders").fetchone()[0])
    assert snapshot["label"] == "Bodega Norte" and snapshot["line"] == "Carretera 57 km 3"
    (document,) = buyer.origin_documents()
    assert document["origin_display"] == "Bodega Norte · San Juan del Río, Querétaro"
    assert document["destination_warehouse_id"] == "wh-1"   # de la OC, no de la sesión

    ok, msg, detail = buyer.origin_create_shipment(document)
    assert ok, msg
    shipment_id = detail["id"]
    assert detail["origin_location"] == "Bodega Norte · San Juan del Río, Querétaro"
    row = conn.execute("SELECT origin_supplier_address_id, destination_warehouse_id"
                       " FROM logistics_shipments").fetchone()
    assert row == ("addr-n", "wh-1")

    # FASE 9: contenedores del bounded context Logística, operados desde escritorio.
    ok, msg, data = buyer.origin_register_container_type(
        code="CAJA-20", name="Caja azul 20 kg", category="PLASTIC_BOX",
        maximum_net_weight=Decimal("25"))
    assert ok, msg
    ok, msg, _ = buyer.origin_register_container(code="cj-0001",
                                                 container_type_id=data["id"])
    assert ok, msg
    ok, msg, detail = buyer.origin_attach_container(shipment_id, "CJ-0001")
    assert ok, msg
    node_id = detail["nodes"][0]["id"]
    (line,) = buyer.origin_loading_lines(shipment_id)
    assert (line["lot_required"], line["weight_required"]) == (True, True)
    assert line["product_name"] == "P1 · Pollo" and line["pending"] == Decimal("10")
    ok, msg, _ = buyer.origin_assign_line(shipment_id, node_id=node_id,
                                          source_line_id=line["source_line_id"],
                                          quantity="10", net_weight="9.8")
    assert not ok and "lote" in msg                       # el producto lo exige
    ok, msg, detail = buyer.origin_assign_line(
        shipment_id, node_id=node_id, source_line_id=line["source_line_id"],
        quantity="10", net_weight="9.8", lot_number="LT-77", temperature="3.5")
    assert ok, msg
    assert detail["differences"] == []
    assert detail["contents"][0]["product_name"] == "P1 · Pollo"
    ok, msg, detail = buyer.origin_seal_root(shipment_id, node_id, "SELLO-1")
    assert ok, msg
    ok, msg, detail = buyer.origin_dispatch(shipment_id)
    assert ok and detail["status"] == "DISPATCHED" and detail["can_mark_transit"]

    # FASE 10: el embarque ya no termina en DISPATCHED.
    ok, msg, detail = buyer.origin_mark_in_transit(shipment_id)
    assert ok and detail["status"] == "IN_TRANSIT"
    ok, msg, detail = buyer.origin_register_arrival(shipment_id)
    assert ok and detail["status"] == "ARRIVED" and detail["can_count"]
    ok, msg, _ = buyer.origin_receive_and_close(shipment_id)
    assert not ok and "Falta contar: P1 · Pollo" in msg
    (arrival,) = buyer.origin_arrival_lines(shipment_id)
    ok, msg, _ = buyer.origin_record_count(
        shipment_id, content_id=arrival["content_id"], received_quantity="10",
        accepted_quantity="9", received_net_weight="9.35", lot_number="",
        piece_count=10)
    assert ok, msg                                     # el lote declarado en origen sirve
    ok, msg, detail = buyer.origin_receive_and_close(shipment_id)
    assert ok, msg
    assert detail["status"] == "CLOSED" and detail["receipts"][0].startswith("REC-")

    # FASE 11: recepción vinculada, trazable, y al inventario sólo lo aceptado.
    receipt = conn.execute("SELECT id, shipment_id, purchase_order_id FROM goods_receipts"
                           ).fetchone()
    assert receipt[1:] == (shipment_id, order_id)
    receipt_line = conn.execute(
        "SELECT received_quantity, accepted_quantity, rejected_quantity, lot, net_weight,"
        " piece_count, temperature FROM goods_receipt_lines").fetchone()
    assert receipt_line == ("10", "9", "1", "LT-77", "9.35", "10", None)
    assert conn.execute("SELECT discrepancy_type FROM receipt_discrepancies").fetchone()[0] \
        == "QUALITY_FAILURE"
    payload = json.loads(conn.execute(
        "SELECT payload_json FROM procurement_outbox WHERE event_name="
        "'GOODS_RECEIPT_COMPLETED'").fetchone()[0])
    (inventory,) = payload["inventory_lines"]
    assert Decimal(inventory["quantity"]) == Decimal("9")          # aceptado, no recibido
    assert (inventory["lot"], inventory["weight"]) == ("LT-77", "9.35")
    assert payload["shipment_id"] == shipment_id
    assert conn.execute("SELECT status FROM logistics_physical_containers").fetchone()[0] \
        == "AVAILABLE"                                           # listo para el siguiente viaje


def test_pickup_order_requires_one_of_the_supplier_warehouses(conn):
    buyer = build_enterprise_presenter(conn, Buyer())
    lines = [{"product_id": "p1", "quantity": "1", "unit_price": "5"}]
    ok, msg, _ = buyer.create_order(supplier_id="s1", branch_id="br-1", warehouse_id="wh-1",
                                    delivery_method="SUPPLIER_PICKUP", lines=lines)
    assert not ok and "bodega o punto de recolección" in msg
    conn.execute("INSERT INTO supplier_addresses (id, supplier_id, address_type, line)"
                 " VALUES ('fiscal','s1','FISCAL','Av. Reforma 1')")
    ok, msg, _ = buyer.create_order(supplier_id="s1", branch_id="br-1", warehouse_id="wh-1",
                                    delivery_method="SUPPLIER_PICKUP",
                                    origin_supplier_address_id="fiscal", lines=lines)
    assert not ok and "no pertenece" in msg        # una dirección fiscal no es bodega
    assert buyer.supplier_origin_options("s1") == [
        ("addr-n", "Bodega Norte · San Juan del Río, Querétaro")]


def test_shipment_without_supplier_warehouse_is_refused(conn):
    buyer = build_enterprise_presenter(conn, Buyer())
    conn.execute("DELETE FROM supplier_addresses")
    ok, msg, data = buyer.create_order(
        supplier_id="s1", branch_id="br-1", warehouse_id="wh-1",
        lines=[{"product_id": "p1", "quantity": "1", "unit_price": "5"}])
    assert ok, msg
    assert build_enterprise_presenter(conn, Approver()).approve_order(data["entity_id"])[0]
    (document,) = buyer.origin_documents()
    ok, msg, _ = buyer.origin_create_shipment(document)
    assert not ok and "no tiene bodegas" in msg


def test_receipt_is_idempotent_and_requires_what_the_product_tracks(conn):
    buyer = build_enterprise_presenter(conn, Buyer())
    order_id = _sent_order(conn, buyer)
    receiver = build_enterprise_presenter(conn, Approver())
    ok, msg, _ = receiver.receive_order(order_id, receipt_lines=[
        {"product_id": "p1", "received_quantity": "4", "accepted_quantity": "4"}])
    assert not ok and "lote" in msg
    ok, msg, _ = receiver.receive_order(order_id, receipt_lines=[
        {"product_id": "p1", "received_quantity": "4", "accepted_quantity": "4",
         "lot": "L1"}])
    assert not ok and "peso" in msg
    uc = receiver._use_cases["po_receive"]
    for _ in range(2):
        result = uc.execute(conn, actor_user_id="user-2", purchase_order_id=order_id,
                            operation_id="op-fixed", receipt_lines=[
                                {"product_id": "p1", "received_quantity": "4",
                                 "accepted_quantity": "4", "lot": "L1", "net_weight": "3.9",
                                 "expiration": "2026-12-31"}])
        assert result.success, result.message
    assert conn.execute("SELECT COUNT(*) FROM goods_receipts").fetchone()[0] == 1
    # la caducidad se guardaba y no se volvía a leer
    from backend.infrastructure.db.repositories.procurement.unit_of_work import (
        ProcurementUnitOfWork,
    )
    receipt_id = conn.execute("SELECT id FROM goods_receipts").fetchone()[0]
    with ProcurementUnitOfWork(conn) as uow:
        assert str(uow.receipts.get(receipt_id).lines[0].expiration) == "2026-12-31"


def test_supplier_address_label_is_captured_and_listed(conn):
    from backend.application.suppliers.queries.supplier_origin_query_service import (
        SupplierOriginQueryService,
    )
    from backend.application.suppliers.use_cases.detail_use_cases import (
        AddSupplierAddressUseCase,
    )
    result = AddSupplierAddressUseCase().execute(
        conn, actor_user_id="user-1", supplier_id="s1", address_type="PICKUP",
        line="Mercado de abastos, bodega 12", operation_id="op-addr", label="Abastos",
        city="Querétaro", state="Querétaro")
    assert result.success, result.message
    displays = [o["display"] for o in SupplierOriginQueryService(conn).origin_locations("s1")]
    assert "Abastos · Querétaro, Querétaro" in displays


def test_closing_a_shipment_with_several_containers(conn):
    """Medido en la base real: al cerrar con DOS contenedores, el historial de
    custodia repetía la misma operación y la tabla (operación única) reventaba."""
    buyer = build_enterprise_presenter(conn, Buyer())
    _sent_order(conn, buyer)
    (document,) = buyer.origin_documents()
    ok, msg, detail = buyer.origin_create_shipment(document)
    assert ok, msg
    shipment_id = detail["id"]
    ok, msg, data = buyer.origin_register_container_type(
        code="HUACAL", name="Huacal", category="CRATE")
    assert ok, msg
    for code in ("HC-1", "HC-2"):
        assert buyer.origin_register_container(code=code, container_type_id=data["id"])[0]
        ok, msg, detail = buyer.origin_attach_container(shipment_id, code)
        assert ok, msg
    (line,) = buyer.origin_loading_lines(shipment_id)
    for node, lot in zip(detail["nodes"], ("L-A", "L-B")):
        ok, msg, detail = buyer.origin_assign_line(
            shipment_id, node_id=node["id"], source_line_id=line["source_line_id"],
            quantity="5", net_weight="5.1", lot_number=lot)
        assert ok, msg
    for node in detail["nodes"]:
        assert buyer.origin_seal_root(shipment_id, node["id"], "S-" + node["id"][-4:])[0]
    for step in (buyer.origin_dispatch, buyer.origin_register_arrival):
        assert step(shipment_id)[0]
    for arrival in buyer.origin_arrival_lines(shipment_id):
        assert buyer.origin_record_count(
            shipment_id, content_id=arrival["content_id"], received_quantity="5",
            accepted_quantity="5", received_net_weight="5.1")[0]
    ok, msg, detail = buyer.origin_receive_and_close(shipment_id)
    assert ok, msg
    assert detail["status"] == "CLOSED"
    lots = {r[0] for r in conn.execute("SELECT lot FROM goods_receipt_lines")}
    assert lots == {"L-A", "L-B"}                          # un renglón por lote
    assert {r[0] for r in conn.execute("SELECT status FROM logistics_physical_containers")} \
        == {"AVAILABLE"}
