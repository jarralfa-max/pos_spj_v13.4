"""Compras FASE 14 — Finanzas/CxP: conciliación de tres vías contra lo que
las fases 5-11 cambiaron en la orden y la recepción.

Reproducido primero en una copia de la base real (2026-09-30):

1. Una orden a $42 con $100 de descuento (neto $40) y $320 de IVA conciliaba una
   factura a $42 SIN IVA: se comparaba el precio bruto y el impuesto de la orden
   nunca se miraba (antes de la FASE 7 la orden no lo guardaba).
2. «A-100», «a-100» y «A-100 » eran facturas distintas; el mismo folio fiscal
   (UUID del CFDI) podía capturarse dos veces.
3. La recepción agrupaba por PRODUCTO: dos líneas del mismo producto tomaban
   cada una el total recibido.
4. La compra rápida «con recepción pendiente» no podía recibirse NUNCA: ni
   inventario, ni factura conciliable, ni CxP.
5. Su recepción está en unidad de inventario (125 kg) y la factura cobra en
   unidad de compra (5 costales): el prellenado proponía facturar 125 costales.
6. «Liberar diferencia» reventaba con TypeError desde la pantalla.
"""

import importlib
import json
import sqlite3
from decimal import Decimal

import pytest

from backend.application.procurement.authorization import PurchaseAuthorizationPolicy
from backend.application.procurement.queries.enterprise_read_services import (
    InvoiceReadService,
)
from backend.application.procurement.use_cases.direct_purchase_use_cases import (
    ConfirmDirectPurchaseUseCase,
    CreateDirectPurchaseUseCase,
    ReceiveDirectPurchaseUseCase,
)
from backend.application.procurement.use_cases.supplier_invoice_use_cases import (
    CaptureSupplierInvoiceUseCase,
    MatchSupplierInvoiceUseCase,
)
from backend.domain.procurement.receiving_matching_policies import (
    allocate_accepted_quantities,
)
from tests.integration.procurement.test_invoice_to_payable_chain import (  # noqa: F401
    _presenters,
    _publish,
    conn,
)

_281 = importlib.import_module("migrations.standalone.281_receipt_line_order_link")


class _AllowAll:
    def has_permission(self, user_id, permission):
        return True


def authorized():
    return PurchaseAuthorizationPolicy(_AllowAll())


def _order(conn, lines, *, receive=None):
    """Orden aprobada y enviada; ``receive`` = {índice de línea: cantidad}."""
    compras, gerente = _presenters(conn)
    for p in (compras, gerente):
        p._dispatch = None
    ok, msg, d = compras.create_order(supplier_id="sup-1", branch_id="br-1",
                                      warehouse_id="wh-1", lines=lines)
    assert ok, msg
    po = d["entity_id"]
    assert gerente.approve_order(po)[0] and compras.send_order(po)[0]
    ids = [r[0] for r in conn.execute(
        "SELECT id FROM purchase_order_lines WHERE purchase_order_id=? ORDER BY id", (po,))]
    if receive:
        ok, msg, _ = compras.receive_order(po, receipt_lines=[{
            "product_id": lines[i]["product_id"], "purchase_order_line_id": ids[i],
            "received_quantity": qty, "accepted_quantity": qty} for i, qty in receive.items()])
        assert ok, msg
    return compras, gerente, po, ids


def _capture(p, po, line, qty, price, tax, number="F-1", uuid=None):
    total = Decimal(qty) * Decimal(price) + Decimal(tax)
    ok, msg, d = p.capture_invoice(
        supplier_id="sup-1", invoice_number=number, total=str(total), purchase_order_id=po,
        uuid_fiscal=uuid, lines=[{"product_id": "p1", "invoiced_quantity": qty,
                                  "unit_price": price, "tax": tax,
                                  "purchase_order_line_id": line}])
    return ok, msg, d.get("entity_id")


_DISCOUNTED = [{"product_id": "p1", "quantity": "50", "unit_price": "42",
                "discount": "100", "tax": "320"}]


class TestNetPriceAndDeclaredTax:
    def test_gross_price_invoice_is_a_price_variance(self, conn):
        compras, gerente, po, (line,) = _order(conn, _DISCOUNTED, receive={0: "30"})
        ok, msg, inv = _capture(compras, po, line, "30", "42", "192")
        assert ok, msg
        assert gerente.match_invoice(inv)[2]["match_result"] == "PRICE_VARIANCE"

    def test_missing_declared_tax_is_a_tax_variance(self, conn):
        compras, gerente, po, (line,) = _order(conn, _DISCOUNTED, receive={0: "30"})
        ok, msg, inv = _capture(compras, po, line, "30", "40", "0")
        assert ok, msg
        assert gerente.match_invoice(inv)[2]["match_result"] == "TAX_VARIANCE"

    def test_net_price_and_prorated_tax_match_into_the_right_payable(self, conn):
        compras, gerente, po, (line,) = _order(conn, _DISCOUNTED, receive={0: "30"})
        (expected,) = compras.invoice_document_profile(po)["lines"]
        assert (expected["unit_price"], expected["tax"], expected["pending_quantity"]) \
            == ("40", "192.00", "30")
        ok, msg, inv = _capture(compras, po, line, "30", "40", "192")
        assert ok, msg
        assert gerente.match_invoice(inv)[2]["match_result"] == "MATCHED"
        _publish(conn)
        assert [r[0] for r in conn.execute("SELECT original_amount FROM payables")] \
            == ["1392.00"]
        detail = compras.invoice_detail(inv)
        assert detail.payable["outstanding_amount"] == "1392.00"

    def test_an_order_without_tax_still_accepts_the_invoice_iva(self, conn):
        compras, gerente, po, (line,) = _order(conn, [
            {"product_id": "p1", "quantity": "10", "unit_price": "50"}], receive={0: "10"})
        ok, msg, inv = _capture(compras, po, line, "10", "50", "80")
        assert ok, msg
        assert gerente.match_invoice(inv)[2]["match_result"] == "MATCHED"

    def test_second_partial_invoice_prefills_only_the_pending_part(self, conn):
        compras, gerente, po, (line,) = _order(conn, _DISCOUNTED, receive={0: "30"})
        assert _capture(compras, po, line, "30", "40", "192", number="A-1")[0]
        compras.receive_order(po, receipt_lines=[{
            "product_id": "p1", "purchase_order_line_id": line,
            "received_quantity": "20", "accepted_quantity": "20"}])
        (expected,) = compras.invoice_document_profile(po)["lines"]
        assert (expected["invoiced_quantity"], expected["pending_quantity"], expected["tax"]) \
            == ("30", "20", "128.00")
        ok, msg, inv = _capture(compras, po, line, "20", "40", "128", number="A-2")
        assert ok, msg
        assert gerente.match_invoice(inv)[2]["match_result"] == "MATCHED"


class TestForeignKeysLikeTheApp:
    def test_receiving_the_rest_of_an_invoiced_order_keeps_working(self, conn):
        """La app abre la base con foreign_keys=ON. Guardar la orden borraba y
        reinsertaba sus líneas: con una factura ya ligada a una línea, recibir
        el resto de la orden fallaba por llave foránea."""
        conn.execute("PRAGMA foreign_keys=ON")
        compras, _, po, (line,) = _order(conn, _DISCOUNTED, receive={0: "30"})
        assert _capture(compras, po, line, "30", "40", "192")[0]
        ok, msg, _ = compras.receive_order(po, receipt_lines=[{
            "product_id": "p1", "purchase_order_line_id": line,
            "received_quantity": "20", "accepted_quantity": "20"}])
        assert ok, msg
        assert conn.execute("SELECT status FROM purchase_orders WHERE id=?",
                            (po,)).fetchone()[0] == "RECEIVED"


class TestAcceptedByOrderLine:
    def test_two_lines_of_the_same_product_do_not_double_count(self, conn):
        compras, gerente, po, (first, second) = _order(conn, [
            {"product_id": "p1", "quantity": "10", "unit_price": "50"},
            {"product_id": "p1", "quantity": "10", "unit_price": "50"}], receive={0: "10"})
        # La segunda línea no recibió nada: facturarla es cobrar lo que no llegó.
        ok, msg, inv = _capture(compras, po, second, "10", "50", "0")
        assert ok, msg
        assert gerente.match_invoice(inv)[2]["match_result"] == "QUANTITY_VARIANCE"
        stored = conn.execute("SELECT purchase_order_line_id FROM goods_receipt_lines"
                              ).fetchall()
        assert [r[0] for r in stored] == [first]

    def test_unlinked_receipts_are_allocated_line_by_line(self):
        result = allocate_accepted_quantities(
            [("a", "p1", Decimal("10")), ("b", "p1", Decimal("10")), ("c", "p2", Decimal("5"))],
            {"c": Decimal("5")}, {"p1": Decimal("14")})
        assert result == {"a": Decimal("10"), "b": Decimal("4"), "c": Decimal("5")}

    def test_migration_281_links_unambiguous_old_receipts(self, conn):
        compras, _, po, (line,) = _order(conn, [
            {"product_id": "p1", "quantity": "10", "unit_price": "50"}], receive={0: "10"})
        conn.execute("UPDATE goods_receipt_lines SET purchase_order_line_id=NULL")
        _281.run(conn)
        assert conn.execute("SELECT purchase_order_line_id FROM goods_receipt_lines"
                            ).fetchone()[0] == line


class TestDuplicates:
    def test_same_number_with_other_case_or_spaces_is_a_duplicate(self, conn):
        compras, _, po, (line,) = _order(conn, [
            {"product_id": "p1", "quantity": "10", "unit_price": "50"}], receive={0: "10"})
        assert _capture(compras, po, line, "5", "50", "0", number="A-100")[0]
        ok, msg, _ = _capture(compras, po, line, "5", "50", "0", number=" a-100 ")
        assert not ok and "duplicada" in msg

    def test_same_fiscal_uuid_is_a_duplicate_even_with_another_number(self, conn):
        compras, _, po, (line,) = _order(conn, [
            {"product_id": "p1", "quantity": "10", "unit_price": "50"}], receive={0: "10"})
        assert _capture(compras, po, line, "5", "50", "0", number="A-1", uuid="ABC-1")[0]
        ok, msg, _ = _capture(compras, po, line, "5", "50", "0", number="A-2", uuid="abc-1")
        assert not ok and "folio fiscal" in msg


class TestReleaseFromTheScreen:
    def test_release_without_the_capturer_argument_no_longer_crashes(self, conn):
        compras, gerente, po, (line,) = _order(conn, [
            {"product_id": "p1", "quantity": "10", "unit_price": "50"}], receive={0: "10"})
        ok, msg, inv = _capture(compras, po, line, "10", "55", "0")
        assert gerente.match_invoice(inv)[2]["match_result"] == "PRICE_VARIANCE"
        ok, msg, _ = gerente.release_variance(inv, reason="Aumento pactado por teléfono")
        assert ok, msg


def _direct(proc_conn, *, mode, quantity="5", factor="1", unit_cost="300"):
    created = CreateDirectPurchaseUseCase(authorized()).execute(
        proc_conn, actor_user_id="u1", operation_id=f"dp-{mode}-{factor}",
        supplier_id="s1", branch_id="br-1", warehouse_id="wh-1", mode=mode,
        payment_condition="SUPPLIER_CREDIT",
        lines=[{"product_id": "p1", "description": "Chile seco", "quantity": quantity,
                "unit_cost": unit_cost, "purchase_unit": "COSTAL", "inventory_unit": "KG",
                "conversion_factor": factor}])
    assert created.success, created.message
    confirmed = ConfirmDirectPurchaseUseCase(authorized()).execute(
        proc_conn, actor_user_id="u1", direct_purchase_id=created.entity_id,
        operation_id=f"confirm-{mode}-{factor}")
    assert confirmed.success, confirmed.message
    return created.entity_id


class TestDeferredDirectReceipt:
    def test_pending_receipt_purchase_can_now_be_received_once(self, proc_conn):
        dp = _direct(proc_conn, mode="DIRECT_WITH_PENDING_RECEIPT")
        receive = ReceiveDirectPurchaseUseCase(authorized())
        first = receive.execute(proc_conn, actor_user_id="u1", direct_purchase_id=dp,
                                operation_id="recv-1")
        assert first.success, first.message
        again = receive.execute(proc_conn, actor_user_id="u1", direct_purchase_id=dp,
                                operation_id="recv-1")
        assert again.success and again.data["goods_receipt_id"] == first.data["goods_receipt_id"]
        other = receive.execute(proc_conn, actor_user_id="u1", direct_purchase_id=dp,
                                operation_id="recv-2")
        assert not other.success
        assert proc_conn.execute("SELECT status FROM direct_purchases WHERE id=?",
                                 (dp,)).fetchone()[0] == "RECEIVED"
        events = [json.loads(r[0]) for r in proc_conn.execute(
            "SELECT payload_json FROM procurement_outbox WHERE event_name="
            "'DIRECT_PURCHASE_RECEIVED'")]
        assert len(events) == 1 and events[0]["goods_receipt_id"] == first.data["goods_receipt_id"]

    def test_an_immediate_receipt_purchase_is_not_received_twice(self, proc_conn):
        dp = _direct(proc_conn, mode="DIRECT_WITH_IMMEDIATE_RECEIPT")
        result = ReceiveDirectPurchaseUseCase(authorized()).execute(
            proc_conn, actor_user_id="u1", direct_purchase_id=dp, operation_id="recv-x")
        assert not result.success

    def test_invoice_matches_only_after_the_deferred_receipt(self, proc_conn):
        dp = _direct(proc_conn, mode="DIRECT_WITH_PENDING_RECEIPT", quantity="5",
                     factor="25")
        line = proc_conn.execute("SELECT id FROM direct_purchase_lines").fetchone()[0]

        def invoice(number):
            captured = CaptureSupplierInvoiceUseCase(authorized()).execute(
                proc_conn, actor_user_id="u1", operation_id=f"cap-{number}",
                supplier_id="s1", invoice_number=number, total="1500",
                direct_purchase_id=dp, lines=[{
                    "product_id": "p1", "invoiced_quantity": "5", "unit_price": "300",
                    "tax": "0", "direct_purchase_line_id": line}])
            assert captured.success, captured.message
            return MatchSupplierInvoiceUseCase(authorized()).execute(
                proc_conn, actor_user_id="u2", operation_id=f"match-{number}",
                invoice_id=captured.entity_id).data["match_result"]

        assert invoice("C-1") == "MISSING_RECEIPT"
        proc_conn.execute("UPDATE supplier_invoices SET status='CANCELLED'")
        assert ReceiveDirectPurchaseUseCase(authorized()).execute(
            proc_conn, actor_user_id="u1", direct_purchase_id=dp,
            operation_id="recv").success
        # 125 kg recibidos = 5 costales facturables (no 125).
        (expected,) = InvoiceReadService(proc_conn).billable_lines("DIRECT_PURCHASE", dp)
        assert (expected["accepted_quantity"], expected["pending_quantity"]) == ("5", "5")
        assert invoice("C-2") == "MATCHED"


@pytest.mark.parametrize("module", [
    "frontend.desktop.modules.purchasing.dialogs.enterprise_dialogs"])
def test_invoice_line_has_no_manual_order_line_field(module):
    source = importlib.import_module(module).__file__
    text = open(source, encoding="utf-8").read()
    assert 'setPlaceholderText("Línea de OC")' not in text


def test_finance_dates_use_the_local_business_day_not_utc():
    """Una factura conciliada a las 20:10 del 30 de septiembre (México) es UTC
    del 1 de octubre: el asiento caía en el periodo de octubre."""
    from datetime import date, timedelta, timezone

    from backend.application.event_handlers.finance import procurement_payable_bridge
    from backend.shared.business_dates import local_business_date

    mexico = timezone(timedelta(hours=-6))
    assert local_business_date("2026-10-01T02:10:00+00:00", tz=mexico) == date(2026, 9, 30)
    assert local_business_date("2026-09-30", tz=mexico) == date(2026, 9, 30)
    assert procurement_payable_bridge._issue_date({"timestamp": "2026-09-30T15:00:00"}) \
        == date(2026, 9, 30)
