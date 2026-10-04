"""Cierre de los pendientes de Compras (2026-09-30), sobre la base NACIDA con el
arranque real (todas las migraciones, incluidas 283-287) y el bus real local.

1. Permisos: LOGISTICA es otorgable (catálogo) y se sembró por función
   (decisión del usuario): gerente todo; almacén sólo ver y RECIBIR.
2. Una sola lista base activa: activar otra REEMPLAZA a la anterior
   (decisión del usuario) y la migración 284 deja «BASE».
3. Surtido de la compra rápida (§11): recolección exige bodega, sólo esas
   compras (confirmadas) van a compra en origen, y el embarque se RECIBE.
4. Recepción fraccionada (§27): la presentación decide.
5. Orden de compra a precio por kg: estimado con el peso nominal, se paga el
   peso real, la factura concilia en kg.
"""

from __future__ import annotations

import importlib
from decimal import Decimal

import pytest

from backend.application.products.commands.product_unit_commands import (
    SetConversionFractionalReceiptCommand,
)
from backend.application.products.use_cases.product_unit_use_cases import (
    SetConversionFractionalReceiptUseCase,
)
from backend.application.security.permission_catalog import CANONICAL_MODULE_PERMISSIONS
from backend.infrastructure.db.repositories.security.permission_repository import (
    SqlitePermissionRepository,
)
from backend.shared.ids import new_uuid
from frontend.desktop.modules.purchasing.direct_purchase_view_models import CartLineVM
from tests.e2e.test_procurement_master_prompt_e2e import (  # noqa: F401
    BRANCH,
    WAREHOUSE,
    _sent_order,
    app,
    env,
    template,
)

_283 = importlib.import_module("migrations.standalone.283_seed_compras_logistica_role_permissions")
_284 = importlib.import_module("migrations.standalone.284_single_active_base_price_list")


def _role_codes(conn, role):
    repo = SqlitePermissionRepository(conn)
    return {code.upper() for code in repo.role_permission_codes(repo.role_id_for_name(role))}


# ── 1 permisos ────────────────────────────────────────────────────────────────
def test_logistics_is_grantable_and_seeded_by_function(env):
    from backend.application.logistics.permissions import ALL_LOGISTICS_PERMISSIONS
    from backend.application.procurement.permissions import ALL_PURCHASE_PERMISSIONS

    assert set(CANONICAL_MODULE_PERMISSIONS["LOGISTICA"]) == {
        code.split(".", 1)[1] for code in ALL_LOGISTICS_PERMISSIONS}
    # La foto de la migración coincide con el vocabulario vivo (sin erratas).
    assert {f"COMPRAS.{a}" for a in _283._COMPRAS} == set(ALL_PURCHASE_PERMISSIONS)
    assert {f"LOGISTICA.{a}" for a in _283._LOGISTICA} == set(ALL_LOGISTICS_PERMISSIONS)

    gerente, almacen = _role_codes(env.conn, "gerente"), _role_codes(env.conn, "almacen")
    assert {"COMPRAS.ORDEN.APROBAR", "LOGISTICA.EMBARQUE.DESPACHAR"} <= gerente
    assert {"COMPRAS.RECEPCION.CREAR", "LOGISTICA.EMBARQUE.RECIBIR"} <= almacen
    assert not {"COMPRAS.ORDEN.CREAR", "COMPRAS.ORDEN.APROBAR", "COMPRAS.FACTURA.CAPTURAR",
                "COMPRAS.FACTURA.LIBERAR_DIFERENCIA", "LOGISTICA.EMBARQUE.CREAR"} & almacen
    assert not {c for c in _role_codes(env.conn, "cajero") if c.startswith("LOGISTICA")}


def test_warehouse_role_can_receive_but_not_order(env):
    from backend.application.logistics.permissions import ALL_LOGISTICS_PERMISSIONS
    from backend.application.procurement.permissions import ALL_PURCHASE_PERMISSIONS

    almacen = _role_codes(env.conn, "almacen")
    # La sesión real normaliza los códigos; aquí se pasan tal como los exige el caso de uso.
    granted = {code for code in ALL_PURCHASE_PERMISSIONS | ALL_LOGISTICS_PERMISSIONS
               if code.upper() in almacen}
    clerk = env.buyer("almacenista", permissions=granted)
    caps = clerk.capabilities()
    assert caps.receipt_complete and caps.origin_receive
    assert not caps.order_create and not caps.invoice_capture
    ok, msg, data = clerk.create_order(supplier_id="sup-1", branch_id=BRANCH,
                                       warehouse_id=WAREHOUSE, lines=[
                                           {"product_id": "p-alas", "quantity": "1",
                                            "unit_price": "40"}])
    assert not ok and data.get("error_code") == "PERMISSION_DENIED"
    _, _, order = _sent_order(env, [{"product_id": "p-alas", "quantity": "5",
                                     "unit_price": "40"}])
    line = clerk.order_detail(order).lines[0].id
    ok, msg, _ = clerk.receive_order(order, receipt_lines=[{
        "product_id": "p-alas", "purchase_order_line_id": line,
        "received_quantity": "5", "accepted_quantity": "5"}])
    assert ok, msg


# ── 2 lista base única ───────────────────────────────────────────────────────
def _base_lists(conn):
    return [r[0] for r in conn.execute("SELECT code FROM price_list WHERE kind='BASE'"
                                       " AND status='ACTIVE' ORDER BY code")]


def test_activating_another_base_list_replaces_the_previous_one(env):
    from backend.application.pricing.use_cases import (
        ActivatePriceListUseCase, ApprovePriceListUseCase, CreatePriceListUseCase,
        SetProductPriceUseCase, SubmitPriceListUseCase,
    )
    before = _base_lists(env.conn)
    created = CreatePriceListUseCase().execute(
        env.conn, actor_user_id="u1", code="NUEVA", name="Lista nueva", kind="BASE",
        operation_id=new_uuid())
    assert created.success, created.message
    # Una lista vacía ya no se aprueba ni se activa: se captura un precio antes.
    priced = SetProductPriceUseCase().execute(
        env.conn, actor_user_id="u1", price_list_id=created.entity_id,
        product_id="p-alas", sale_price="44", operation_id=new_uuid())
    assert priced.success, priced.message
    for use_case, actor in ((SubmitPriceListUseCase, "u1"), (ApprovePriceListUseCase, "u2"),
                            (ActivatePriceListUseCase, "u2")):
        result = use_case().execute(env.conn, actor_user_id=actor,
                                    price_list_id=created.entity_id, operation_id=new_uuid())
        assert result.success, result.message
    assert _base_lists(env.conn) == ["NUEVA"]
    assert len(before) <= 1


def test_migration_284_keeps_the_list_called_base(env):
    # La 284 opera sobre bases ANTERIORES al índice único de la 299, que hoy
    # impide fabricar dos listas base activas: se simula esa base soltándolo.
    env.conn.execute("DROP INDEX IF EXISTS ux_price_list_single_active_base")
    now = "2026-09-25T04:20:52"
    env.conn.execute("INSERT INTO price_list (id, code, name, kind, status, discount_pct,"
                     " created_at, updated_at) VALUES (?, 'ORIGIN-00001', 'Lista Origina{',"
                     " 'BASE', 'ACTIVE', '0', ?, ?)", (new_uuid(), now, now))
    if "BASE" not in _base_lists(env.conn):
        env.conn.execute("INSERT INTO price_list (id, code, name, kind, status, discount_pct,"
                         " created_at) VALUES (?, 'BASE', 'Lista base', 'BASE', 'ACTIVE', '0',"
                         " '2026-09-25 02:23:47')", (new_uuid(),))
    _284.run(env.conn)
    assert _base_lists(env.conn) == ["BASE"]


# ── 3 surtido de la compra rápida ────────────────────────────────────────────
def test_supplier_pickup_requires_origin_and_flows_through_origin_purchase(env):
    direct = env.direct()
    line = CartLineVM("p-alas", "Alas", Decimal("10"), Decimal("44"))
    ok, msg, data = direct.create(supplier_id="sup-1", lines=[line], mode="",
                                  fulfillment_mode="SUPPLIER_PICKUP",
                                  payment_condition="SUPPLIER_CREDIT", branch_id=BRANCH,
                                  warehouse_id=WAREHOUSE)
    assert not ok and data["error_code"] == "ORIGIN_REQUIRED"
    assert direct.supplier_origin_options("sup-1") == [
        ("addr-1", "Bodega Norte · San Juan del Río, Querétaro")]
    ok, msg, data = direct.create(supplier_id="sup-1", lines=[line], mode="",
                                  fulfillment_mode="SUPPLIER_PICKUP",
                                  origin_supplier_address_id="addr-1",
                                  payment_condition="SUPPLIER_CREDIT", branch_id=BRANCH,
                                  warehouse_id=WAREHOUSE)
    assert ok, msg
    dp = data["entity_id"]
    detail = direct.detail(dp)
    assert detail.mode == "DIRECT_WITH_PENDING_RECEIPT"
    assert (detail.fulfillment_mode, detail.origin_display) == (
        "SUPPLIER_PICKUP", "Bodega Norte · San Juan del Río, Querétaro")

    buyer = env.buyer()
    assert not [d for d in buyer.origin_documents() if d["id"] == dp]   # borrador: no
    assert direct.confirm(dp, None)[0]
    (document,) = [d for d in buyer.origin_documents() if d["id"] == dp]
    assert document["origin_supplier_address_id"] == "addr-1"
    ok, msg, detail = buyer.origin_create_shipment(document)
    assert ok, msg
    shipment = detail["id"]
    ok, msg, kind = buyer.origin_register_container_type(code="CAJA", name="Caja",
                                                         category="CRATE")
    assert buyer.origin_register_container(code="CJ-1", container_type_id=kind["id"])[0]
    ok, msg, detail = buyer.origin_attach_container(shipment, "CJ-1")
    (loading,) = buyer.origin_loading_lines(shipment)
    ok, msg, detail = buyer.origin_assign_line(
        shipment, node_id=detail["nodes"][0]["id"], source_line_id=loading["source_line_id"],
        quantity="10", net_weight="10.2", lot_number="L-D")
    assert ok, msg
    assert buyer.origin_seal_root(shipment, detail["nodes"][0]["id"], "S-9")[0]
    for step in (buyer.origin_dispatch, buyer.origin_mark_in_transit,
                 buyer.origin_register_arrival):
        assert step(shipment)[0]
    (arrival,) = buyer.origin_arrival_lines(shipment)
    assert buyer.origin_record_count(shipment, content_id=arrival["content_id"],
                                     received_quantity="10", accepted_quantity="9",
                                     received_net_weight="10.2")[0]
    ok, msg, detail = buyer.origin_receive_and_close(shipment)
    assert ok, msg                                   # antes: «todavía no está disponible»
    assert env.stock("p-alas") == Decimal("9")
    assert env.conn.execute("SELECT status FROM direct_purchases WHERE id=?",
                            (dp,)).fetchone()[0] == "RECEIVED"
    lot = env.conn.execute("SELECT r.lot, r.rejected_quantity FROM goods_receipt_lines r"
                           " JOIN goods_receipts g ON g.id=r.goods_receipt_id"
                           " WHERE g.direct_purchase_id=?", (dp,)).fetchone()
    assert (lot[0], Decimal(lot[1])) == ("L-D", Decimal("1"))


def test_immediate_receipt_is_still_the_default(env):
    direct = env.direct()
    ok, msg, data = direct.create(supplier_id="sup-1", mode="DIRECT_WITH_IMMEDIATE_RECEIPT",
                                  payment_condition="SUPPLIER_CREDIT", branch_id=BRANCH,
                                  warehouse_id=WAREHOUSE,
                                  lines=[CartLineVM("p-alas", "Alas", Decimal("1"),
                                                    Decimal("40"))])
    assert ok, msg
    assert direct.detail(data["entity_id"]).fulfillment_mode == "IMMEDIATE_RECEIPT"


# ── 4 recepción fraccionada ──────────────────────────────────────────────────
def _sack_conversion(conn):
    return conn.execute("SELECT id FROM product_unit_conversions WHERE product_id='p-chile'"
                        ).fetchone()[0]


def test_fractional_receipt_policy_comes_from_the_presentation(env):
    buyer, _, order = _sent_order(env, [{"product_id": "p-chile", "quantity": "5",
                                         "unit_price": "300", "purchase_unit": "COSTAL"}])
    line = buyer.order_detail(order).lines[0].id
    receipt = [{"product_id": "p-chile", "purchase_order_line_id": line,
                "received_quantity": "4.88", "accepted_quantity": "4.88"}]  # 4 + 22 kg
    result = SetConversionFractionalReceiptUseCase(env.conn).execute(
        SetConversionFractionalReceiptCommand(operation_id=new_uuid(),
                                              conversion_id=_sack_conversion(env.conn),
                                              fractional_receipt=False, user_id="u1"))
    assert result.success
    ok, msg, _ = buyer.receive_order(order, receipt_lines=receipt)
    assert not ok and "completos" in msg
    SetConversionFractionalReceiptUseCase(env.conn).execute(
        SetConversionFractionalReceiptCommand(operation_id=new_uuid(),
                                              conversion_id=_sack_conversion(env.conn),
                                              fractional_receipt=True, user_id="u1"))
    ok, msg, _ = buyer.receive_order(order, receipt_lines=receipt)
    assert ok, msg
    assert env.stock("p-chile") == Decimal("122")                     # 4.88 × 25 kg


def test_receive_dialog_turns_loose_kilograms_into_sacks(env, app):
    from frontend.desktop.modules.purchasing.dialogs.enterprise_dialogs import (
        ReceiveOrderDialog,
        ReceiveOrderLineDialog,
    )
    buyer, _, order = _sent_order(env, [{"product_id": "p-chile", "quantity": "5",
                                         "unit_price": "300", "purchase_unit": "COSTAL"}])
    dialog = ReceiveOrderDialog(None, order_detail=buyer.order_detail(order),
                                profile_provider=buyer.purchase_profile)
    (capture,) = dialog._captures
    line_dialog = ReceiveOrderLineDialog(None, capture=capture)
    assert line_dialog._loose is not None
    line_dialog._received.set_decimal("4")
    line_dialog._accepted.set_decimal("4")
    line_dialog._loose.set_decimal("22")
    assert line_dialog.values()["received"] == "4.88"


# ── 5 orden a precio por kg ──────────────────────────────────────────────────
def test_variable_weight_order_pays_the_real_weight(env):
    buyer, approver, order = _sent_order(env, [{"product_id": "p-res", "quantity": "5",
                                                "unit_price": "95", "purchase_unit": "CAJA"}])
    detail = buyer.order_detail(order)
    assert Decimal(detail.total) == Decimal("11875")                  # 5 × 25 kg × $95
    line = detail.lines[0].id
    ok, msg, _ = buyer.receive_order(order, receipt_lines=[{
        "product_id": "p-res", "purchase_order_line_id": line, "received_quantity": "5",
        "accepted_quantity": "5", "net_weight": "127.850"}])
    assert ok, msg
    assert env.stock("p-res") == Decimal("127.850")
    assert env.average_cost("p-res") == Decimal("95.00")
    (expected,) = buyer.invoice_document_profile(order)["lines"]
    assert (expected["purchase_unit"], expected["pending_quantity"], expected["unit_price"]) \
        == ("KG", "127.85", "95")
    ok, msg, invoice = buyer.capture_invoice(
        supplier_id="sup-1", invoice_number="R-1", total="12145.75", purchase_order_id=order,
        lines=[{"product_id": "p-res", "invoiced_quantity": "127.850", "unit_price": "95",
                "tax": "0", "purchase_order_line_id": line}])
    assert ok, msg
    assert approver.match_invoice(invoice["entity_id"])[2]["match_result"] == "MATCHED"
