"""Auditoría directa de Compras d9f2bca — un caso por escenario del anexo.

Cada prueba reproduce lo que la auditoría observó y fija el criterio de
aceptación corregido (C01–C24). Las pruebas de UI/navegación (C25/C26) viven
en las suites de pantalla.
"""

import json
from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend.application.procurement.authorization import PurchaseAuthorizationPolicy
from backend.application.procurement.integrations.procurement_outbox_dispatcher import (
    dispatch_procurement_outbox,
)
from backend.application.procurement.integrations.wiring import wire_procurement
from backend.application.procurement.permissions import PurchasePermissions as P
from backend.application.procurement.session_authorization import (
    ProcurementSessionPermissionChecker,
)
from backend.application.procurement.use_cases.award_order_use_cases import (
    GeneratePurchaseOrdersFromAwardUseCase,
)
from backend.application.procurement.use_cases.direct_purchase_use_cases import (
    ConfirmDirectPurchaseUseCase,
    CreateDirectPurchaseUseCase,
    ReceiveDirectPurchaseUseCase,
)
from backend.application.procurement.use_cases.purchase_order_use_cases import (
    ApprovePurchaseOrderUseCase,
    CreatePurchaseOrderUseCase,
    ReceivePurchaseOrderUseCase,
    ReverseGoodsReceiptUseCase,
    SendPurchaseOrderUseCase,
)
from backend.application.procurement.use_cases.purchase_return_use_cases import (
    CreatePurchaseReturnUseCase,
)
from backend.application.procurement.use_cases.quotation_use_cases import (
    AwardSupplierQuoteUseCase,
    CaptureSupplierQuoteUseCase,
    CreateRfqUseCase,
)
from backend.application.procurement.use_cases.remainder_use_cases import (
    CancelSupplierInvoiceUseCase,
)
from backend.application.procurement.use_cases.requisition_use_cases import (
    ApprovePurchaseRequisitionUseCase,
    CreatePurchaseRequisitionUseCase,
    SubmitPurchaseRequisitionUseCase,
)
from backend.application.procurement.use_cases.supplier_invoice_use_cases import (
    CaptureSupplierInvoiceUseCase,
    MatchSupplierInvoiceUseCase,
)
from backend.domain.procurement.exceptions import InvalidMoneyError
from backend.domain.procurement.value_objects import Money, PurchaseLimit
from backend.infrastructure.db.repositories.procurement.unit_of_work import (
    ProcurementUnitOfWork,
)
from backend.infrastructure.db.schema.procurement_schema import create_purchase_returns_schema
from backend.shared.events.application_bus import ApplicationEventBus
from backend.shared.ids import derived_uuidv7, new_uuid


class _Deny:
    def __init__(self, *denied):
        self._denied = set(denied)

    def has_permission(self, user_id, code):
        return code not in self._denied


def _order(conn, *, lines=None, supplier="s1", branch="br-1", currency="MXN", op=None,
           **header):
    created = CreatePurchaseOrderUseCase().execute(
        conn, actor_user_id="buyer", operation_id=op or new_uuid(), supplier_id=supplier,
        branch_id=branch, warehouse_id="wh-1", currency_code=currency,
        lines=lines or [{"product_id": "p1", "quantity": "10", "unit_price": "10"}],
        **header)
    assert created.success, created.message
    ApprovePurchaseOrderUseCase().execute(conn, approver_user_id="jefe",
                                          purchase_order_id=created.entity_id,
                                          operation_id=new_uuid())
    SendPurchaseOrderUseCase().execute(conn, actor_user_id="buyer",
                                       purchase_order_id=created.entity_id,
                                       operation_id=new_uuid())
    return created.entity_id


def _line(conn, po, index=0):
    return conn.execute("SELECT id FROM purchase_order_lines WHERE purchase_order_id=?"
                        " ORDER BY rowid", (po,)).fetchall()[index][0]


def _receive(conn, po, lines, auth=None):
    return ReceivePurchaseOrderUseCase(authorization=auth).execute(
        conn, actor_user_id="alm", purchase_order_id=po, operation_id=new_uuid(),
        receipt_lines=lines)


def _status(conn, po):
    return conn.execute("SELECT status FROM purchase_orders WHERE id=?", (po,)).fetchone()[0]


def _outbox(conn, event):
    return [json.loads(row[0]) for row in conn.execute(
        "SELECT payload_json FROM procurement_outbox WHERE event_name=? ORDER BY created_at",
        (event,))]


# ── C01 ──────────────────────────────────────────────────────────────────────
class TestC01DeliveryIsConfirmed:
    def _receipt_event(self, conn):
        po = _order(conn)
        assert _receive(conn, po, [{"product_id": "p1", "received_quantity": "10"}]).success

    def test_failing_consumer_keeps_the_row_pending(self, proc_conn):
        self._receipt_event(proc_conn)
        bus = ApplicationEventBus()
        wire_procurement(bus, proc_conn)
        bus.subscribe("PURCHASE_STOCK_ENTRY_REGISTERED",
                      lambda _p: (_ for _ in ()).throw(RuntimeError("inventario caído")))
        summary = dispatch_procurement_outbox(proc_conn, bus)
        assert summary["failed"] >= 1
        row = proc_conn.execute(
            "SELECT status, attempt_count FROM procurement_outbox"
            " WHERE event_name='GOODS_RECEIPT_COMPLETED'").fetchone()
        assert row[0] == "PENDING" and row[1] == 1

    def test_no_subscriber_is_not_delivered(self, proc_conn):
        self._receipt_event(proc_conn)
        dispatch_procurement_outbox(proc_conn, ApplicationEventBus())
        assert proc_conn.execute(
            "SELECT status FROM procurement_outbox WHERE event_name='GOODS_RECEIPT_COMPLETED'"
        ).fetchone()[0] == "PENDING"

    def test_derived_event_identity_is_stable_across_retries(self):
        source = new_uuid()
        assert derived_uuidv7(source, "X") == derived_uuidv7(source, "X")
        assert derived_uuidv7(source, "X") != derived_uuidv7(source, "Y")


# ── C02 / C03 / C04 / C21 / C22 ──────────────────────────────────────────────
class TestInvoiceIdentityAndQuantities:
    def _received(self, conn, **order):
        po = _order(conn, **order)
        assert _receive(conn, po, [{"product_id": "p1", "received_quantity": "10"}]).success
        return po, _line(conn, po)

    def _capture(self, conn, po, line, *, supplier="s1", currency="MXN", product="p1",
                 lines=None, total="100", number=None):
        return CaptureSupplierInvoiceUseCase().execute(
            conn, actor_user_id="cxp", operation_id=new_uuid(), supplier_id=supplier,
            invoice_number=number or new_uuid()[-12:], total=total, currency_code=currency,
            purchase_order_id=po,
            lines=lines or [{"product_id": product, "invoiced_quantity": "10",
                             "unit_price": "10", "purchase_order_line_id": line}])

    @pytest.mark.parametrize("change,code", [
        ({"supplier": "s2"}, "SUPPLIER_MISMATCH"),
        ({"currency": "USD"}, "CURRENCY_MISMATCH"),
        ({"product": "p9"}, "PRODUCT_MISMATCH"),
    ])
    def test_wrong_identity_never_matches(self, proc_conn, change, code):
        po, line = self._received(proc_conn)
        result = self._capture(proc_conn, po, line, **change)
        assert not result.success and result.error_code == code

    def test_two_lines_on_one_source_cannot_bill_it_twice(self, proc_conn):
        po, line = self._received(proc_conn)
        inv = self._capture(proc_conn, po, line, total="200", lines=[
            {"product_id": "p1", "invoiced_quantity": "10", "unit_price": "10",
             "purchase_order_line_id": line}] * 2)
        result = MatchSupplierInvoiceUseCase().execute(
            proc_conn, actor_user_id="cxp", operation_id=new_uuid(), invoice_id=inv.entity_id)
        assert result.data["match_result"] == "QUANTITY_VARIANCE"

    def test_asset_nature_survives_save_and_reaches_finance(self, proc_conn):
        po, line = self._received(proc_conn, lines=[
            {"product_id": "p1", "quantity": "10", "unit_price": "10",
             "purchase_nature": "ASSET"}])
        inv = self._capture(proc_conn, po, line, lines=[
            {"product_id": "p1", "invoiced_quantity": "10", "unit_price": "10",
             "purchase_order_line_id": line}])   # sin naturaleza: se toma del origen
        MatchSupplierInvoiceUseCase().execute(
            proc_conn, actor_user_id="cxp", operation_id=new_uuid(), invoice_id=inv.entity_id)
        with ProcurementUnitOfWork(proc_conn) as uow:
            assert uow.invoices.get(inv.entity_id).lines[0].purchase_nature.value == "ASSET"
        (payable,) = _outbox(proc_conn, "ACCOUNT_PAYABLE_CREATE_REQUESTED")
        assert payable["nature_subtotals"] == {"ASSET": "100"}

    def test_match_actor_is_kept_on_the_header(self, proc_conn):
        po, line = self._received(proc_conn)
        inv = self._capture(proc_conn, po, line)
        MatchSupplierInvoiceUseCase().execute(
            proc_conn, actor_user_id="conciliador", operation_id=new_uuid(),
            invoice_id=inv.entity_id)
        assert proc_conn.execute("SELECT matched_by_user_id FROM supplier_invoices WHERE id=?",
                                 (inv.entity_id,)).fetchone()[0] == "conciliador"

    def test_unmatched_draft_does_not_consume_and_can_be_cancelled(self, proc_conn):
        po, line = self._received(proc_conn)
        draft = self._capture(proc_conn, po, line)
        good = self._capture(proc_conn, po, line)
        result = MatchSupplierInvoiceUseCase().execute(
            proc_conn, actor_user_id="cxp", operation_id=new_uuid(), invoice_id=good.entity_id)
        assert result.data["match_result"] == "MATCHED"
        cancelled = CancelSupplierInvoiceUseCase().execute(
            proc_conn, actor_user_id="cxp", invoice_id=draft.entity_id,
            operation_id=new_uuid(), reason="capturada por error")
        assert cancelled.success


# ── C04 / C05 / C06 / C10 / C14 / C17 (compra directa) ───────────────────────
class TestDirectPurchase:
    def _direct(self, conn, lines, *, mode="DIRECT_WITH_IMMEDIATE_RECEIPT",
                payment="SUPPLIER_CREDIT", **kw):
        created = CreateDirectPurchaseUseCase(**kw).execute(
            conn, actor_user_id="u1", operation_id=new_uuid(), supplier_id="s1",
            branch_id="br-1", warehouse_id="wh-1", lines=lines, mode=mode,
            payment_condition=payment)
        assert created.success, created.message
        return created

    def test_expense_line_does_not_enter_stock(self, proc_conn):
        dp = self._direct(proc_conn, [
            {"product_id": "p1", "quantity": "1", "unit_cost": "100",
             "purchase_nature": "EXPENSE"}])
        assert ConfirmDirectPurchaseUseCase().execute(
            proc_conn, actor_user_id="u1", direct_purchase_id=dp.entity_id,
            operation_id=new_uuid()).success
        (received,) = _outbox(proc_conn, "DIRECT_PURCHASE_RECEIVED")
        assert received["inventory_lines"] == []

    def test_discount_is_net_in_payment_split_and_inventory_cost(self, proc_conn):
        dp = self._direct(proc_conn, [
            {"product_id": "p1", "quantity": "10", "unit_cost": "10", "discount": "10"}],
            payment="IMMEDIATE_PAYMENT")
        assert ConfirmDirectPurchaseUseCase().execute(
            proc_conn, actor_user_id="u1", direct_purchase_id=dp.entity_id,
            operation_id=new_uuid(), payment_source="BANK_TRANSFER").success
        (payment,) = _outbox(proc_conn, "PURCHASE_PAYMENT_REQUESTED")
        assert payment["amount"] == "90" or Decimal(payment["amount"]) == Decimal("90")
        assert {k: Decimal(v) for k, v in payment["nature_subtotals"].items()} == {
            "INVENTORY": Decimal("90")}
        (received,) = _outbox(proc_conn, "DIRECT_PURCHASE_RECEIVED")
        assert Decimal(received["inventory_lines"][0]["unit_cost"]) == Decimal("9")

    def test_partial_receipt_keeps_the_rest_pending(self, proc_conn):
        dp = self._direct(proc_conn, [{"product_id": "p1", "quantity": "10", "unit_cost": "5"}],
                          mode="DIRECT_WITH_PENDING_RECEIPT")
        ConfirmDirectPurchaseUseCase().execute(proc_conn, actor_user_id="u1",
                                               direct_purchase_id=dp.entity_id,
                                               operation_id=new_uuid())
        line = proc_conn.execute("SELECT id FROM direct_purchase_lines").fetchone()[0]
        receive = ReceiveDirectPurchaseUseCase()
        first = receive.execute(proc_conn, actor_user_id="alm", direct_purchase_id=dp.entity_id,
                                operation_id=new_uuid(), receipt_lines=[
                                    {"direct_purchase_line_id": line, "received_quantity": "4"}])
        assert first.data["status"] == "PARTIALLY_RECEIVED"
        second = receive.execute(proc_conn, actor_user_id="alm", direct_purchase_id=dp.entity_id,
                                 operation_id=new_uuid())   # recibe lo pendiente (6)
        assert second.data["status"] == "RECEIVED"
        quantities = [Decimal(e["inventory_lines"][0]["quantity"])
                      for e in _outbox(proc_conn, "DIRECT_PURCHASE_RECEIVED")]
        assert quantities == [Decimal("4"), Decimal("6")]

    def test_traceability_profile_is_enforced_on_direct_receipt(self, proc_conn):
        profile = SimpleNamespace(name="Pollo", lot_controlled=True, expiration_controlled=False,
                                  catch_weight=False, temperature_tracked=False)
        catalog = SimpleNamespace(purchase_profile=lambda _pid: profile,
                                  resolve=lambda _pid: SimpleNamespace(purchasable=True))
        dp = self._direct(proc_conn, [{"product_id": "p1", "quantity": "2", "unit_cost": "5"}])
        result = ConfirmDirectPurchaseUseCase(product_catalog=catalog).execute(
            proc_conn, actor_user_id="u1", direct_purchase_id=dp.entity_id,
            operation_id=new_uuid())
        assert not result.success and result.error_code == "TRACEABILITY_REQUIRED"

    def test_daily_limit_requires_authorization(self, proc_conn):
        with ProcurementUnitOfWork(proc_conn) as uow:
            uow.limits.upsert_user_limit(user_id="u1", limit=PurchaseLimit(
                currency_code="MXN", maximum_per_transaction=None,
                maximum_per_day=Decimal("50"), maximum_per_month=Decimal("50"),
                requires_approval_above=None))
        created = self._direct(proc_conn, [{"product_id": "p1", "quantity": "10",
                                            "unit_cost": "10"}])
        assert created.data["requires_authorization"] is True


# ── C07 / C08 / C09 / C11 (recepción de orden) ───────────────────────────────
class TestOrderReceipt:
    def test_split_over_delivery_still_needs_authorization(self, proc_conn):
        po = _order(proc_conn)
        strict = PurchaseAuthorizationPolicy(_Deny(P.RECEIPT_OVER_TOLERANCE))
        assert _receive(proc_conn, po, [{"product_id": "p1", "received_quantity": "6"}],
                        strict).success
        second = _receive(proc_conn, po, [{"product_id": "p1", "received_quantity": "6"}],
                          strict)
        assert not second.success and second.error_code == "OVER_TOLERANCE"

    def test_wrong_product_and_negative_quantities_are_rejected(self, proc_conn):
        po = _order(proc_conn)
        line = _line(proc_conn, po)
        wrong = _receive(proc_conn, po, [{"product_id": "p9", "purchase_order_line_id": line,
                                          "received_quantity": "1"}])
        negative = _receive(proc_conn, po, [{"product_id": "p1", "received_quantity": "-2",
                                             "accepted_quantity": "-2"}])
        assert wrong.error_code == "PRODUCT_MISMATCH" and negative.error_code == "VALIDATION"
        assert proc_conn.execute("SELECT COUNT(*) FROM goods_receipts").fetchone()[0] == 0

    def test_fully_rejected_delivery_keeps_the_order_open_for_replacement(self, proc_conn):
        po = _order(proc_conn)
        _receive(proc_conn, po, [{"product_id": "p1", "received_quantity": "10",
                                  "accepted_quantity": "0"}])
        assert _status(proc_conn, po) == "PARTIALLY_RECEIVED"
        assert _receive(proc_conn, po, [{"product_id": "p1", "received_quantity": "10"}]).success
        assert _status(proc_conn, po) == "RECEIVED"

    def test_reversal_undoes_every_lot_and_each_source_line(self, proc_conn):
        po = _order(proc_conn, lines=[
            {"product_id": "p1", "quantity": "10", "unit_price": "10"},
            {"product_id": "p1", "quantity": "5", "unit_price": "10"}])
        first, second = _line(proc_conn, po, 0), _line(proc_conn, po, 1)
        receipt = _receive(proc_conn, po, [
            {"product_id": "p1", "purchase_order_line_id": first, "received_quantity": "5",
             "lot": "A"},
            {"product_id": "p1", "purchase_order_line_id": first, "received_quantity": "5",
             "lot": "B"},
            {"product_id": "p1", "purchase_order_line_id": second, "received_quantity": "5"}])
        assert ReverseGoodsReceiptUseCase().execute(
            proc_conn, actor_user_id="jefe", goods_receipt_id=receipt.entity_id,
            operation_id=new_uuid(), reason="captura duplicada").success
        rows = proc_conn.execute("SELECT received_quantity, accepted_quantity FROM"
                                 " purchase_order_lines WHERE purchase_order_id=?",
                                 (po,)).fetchall()
        assert all(Decimal(r[0]) == 0 and Decimal(r[1]) == 0 for r in rows)


# ── C12 / C13 (reversos y devoluciones) ──────────────────────────────────────
class TestReturns:
    def test_return_validates_origin_and_returnable_quantity(self, proc_conn):
        create_purchase_returns_schema(proc_conn)
        po = _order(proc_conn)
        receipt = _receive(proc_conn, po, [{"product_id": "p1", "received_quantity": "10"}])
        uc = CreatePurchaseReturnUseCase()

        def attempt(**overrides):
            kw = dict(actor_user_id="alm", operation_id=new_uuid(), supplier_id="s1",
                      branch_id="br-1", warehouse_id="wh-1", reason="DAMAGED",
                      goods_receipt_id=receipt.entity_id,
                      lines=[{"product_id": "p1", "quantity": "3"}])
            kw.update(overrides)
            return uc.execute(proc_conn, **kw)

        assert attempt(lines=[{"product_id": "p1", "quantity": "1000"}]).error_code == \
            "OVER_RETURN"
        assert attempt(supplier_id="s2").error_code == "SUPPLIER_MISMATCH"
        assert not attempt(lines=[{"product_id": "p9", "quantity": "1"}]).success
        assert attempt().success

    def test_compensation_consumers_are_wired_and_drafts_do_not_move_stock(self):
        from backend.application.event_handlers.inventory.supplier_return_handler import (
            SupplierReturnHandler,
        )
        from backend.bootstrap.wiring.event_wiring import wire_procurement_downstream_bridges

        bus = ApplicationEventBus()
        wire_procurement_downstream_bridges(bus, connection=None)
        for event in ("GOODS_RECEIPT_REVERSED", "DIRECT_PURCHASE_REVERSED",
                      "PURCHASE_RETURN_CONFIRMED"):
            assert bus.subscriptions_for(event), event
        assert not bus.subscriptions_for("PURCHASE_RETURN_CREATED")
        assert SupplierReturnHandler.event_name == "PURCHASE_RETURN_CONFIRMED"


# ── C15 / C16 (adjudicación) ─────────────────────────────────────────────────
class TestAward:
    def _rfq(self, conn, *, currency="MXN"):
        req = CreatePurchaseRequisitionUseCase().execute(
            conn, actor_user_id="req", operation_id=new_uuid(), branch_id="br-1",
            purchase_type="INVENTORY", lines=[{"product_id": "p1", "quantity": "2"}])
        SubmitPurchaseRequisitionUseCase().execute(conn, actor_user_id="req",
                                                   requisition_id=req.entity_id,
                                                   operation_id=new_uuid())
        ApprovePurchaseRequisitionUseCase().execute(conn, approver_user_id="jefe",
                                                    requisition_id=req.entity_id,
                                                    operation_id=new_uuid())
        rfq = CreateRfqUseCase().execute(conn, actor_user_id="u1", operation_id=new_uuid(),
                                         supplier_ids=["s1", "s2"],
                                         requisition_id=req.entity_id)
        quote = CaptureSupplierQuoteUseCase().execute(
            conn, actor_user_id="u1", operation_id=new_uuid(), rfq_id=rfq.entity_id,
            supplier_id="s1", currency_code=currency,
            lines=[{"product_id": "p1", "quantity": "2", "unit_price": "10",
                    "discount": "2", "tax": "1"}])
        line = conn.execute("SELECT id FROM supplier_quote_lines WHERE quote_id=?",
                            (quote.entity_id,)).fetchone()[0]
        return quote.entity_id, line

    def _award(self, conn, line, *, supplier="s1", quantity="2"):
        return AwardSupplierQuoteUseCase().execute(
            conn, actor_user_id="u1", operation_id=new_uuid(), reason="precio",
            award_lines=[{"quote_line_id": line, "supplier_id": supplier,
                          "awarded_quantity": quantity, "justification": "precio"}])

    def test_wrong_supplier_excess_and_second_award_are_rejected(self, proc_conn):
        _quote, line = self._rfq(proc_conn)
        assert self._award(proc_conn, line, supplier="s2").error_code == "SUPPLIER_MISMATCH"
        assert self._award(proc_conn, line, quantity="1000").error_code == "OVER_AWARD"
        assert self._award(proc_conn, line).success
        assert self._award(proc_conn, line).error_code == "ALREADY_AWARDED"

    def test_order_keeps_quoted_currency_discount_and_tax(self, proc_conn):
        _quote, line = self._rfq(proc_conn, currency="USD")
        award = self._award(proc_conn, line)
        result = GeneratePurchaseOrdersFromAwardUseCase(CreatePurchaseOrderUseCase()).execute(
            proc_conn, actor_user_id="buyer", operation_id=new_uuid(),
            award_id=award.entity_id, warehouse_id="wh-1", exchange_rate="18.5")
        assert result.success, result.message
        with ProcurementUnitOfWork(proc_conn) as uow:
            order = uow.orders.get(result.data["orders"][0]["entity_id"])
        assert order.currency_code == "USD"
        assert order.total().amount == Decimal("19.00")


# ── C18 / C19 / C20 / C23 ────────────────────────────────────────────────────
class TestControlsAndContracts:
    def test_session_cannot_operate_another_branch(self, proc_conn):
        session = SimpleNamespace(user_id="u1", is_active=True, active_branch_id="br-1",
                                  assigned_branch_ids=(),
                                  tiene_permiso=lambda code: code in {P.VIEW, P.ORDER_CREATE})
        auth = PurchaseAuthorizationPolicy(ProcurementSessionPermissionChecker(session))
        result = CreatePurchaseOrderUseCase(auth).execute(
            proc_conn, actor_user_id="u1", operation_id=new_uuid(), supplier_id="s1",
            branch_id="br-2", warehouse_id="wh-1",
            lines=[{"product_id": "p1", "quantity": "1", "unit_price": "1"}])
        assert not result.success and result.error_code == "PERMISSION_DENIED"

    def test_reused_key_with_other_content_is_a_conflict(self, proc_conn):
        op = new_uuid()
        base = dict(actor_user_id="u1", operation_id=op, supplier_id="s1", branch_id="br-1",
                    warehouse_id="wh-1")
        uc = CreatePurchaseOrderUseCase()
        assert uc.execute(proc_conn, **base, lines=[
            {"product_id": "p1", "quantity": "10", "unit_price": "1"}]).success
        assert uc.execute(proc_conn, **base, lines=[
            {"product_id": "p1", "quantity": "10", "unit_price": "1"}]).success
        clash = uc.execute(proc_conn, **base, lines=[
            {"product_id": "p1", "quantity": "200", "unit_price": "1"}])
        assert clash.error_code == "IDEMPOTENCY_CONFLICT"

    def test_nested_use_case_does_not_commit_the_coordinator(self, proc_conn):
        with pytest.raises(RuntimeError):
            with ProcurementUnitOfWork(proc_conn):
                assert CreatePurchaseOrderUseCase().execute(
                    proc_conn, actor_user_id="u1", operation_id=new_uuid(),
                    supplier_id="s1", branch_id="br-1", warehouse_id="wh-1",
                    lines=[{"product_id": "p1", "quantity": "1", "unit_price": "1"}]).success
                raise RuntimeError("el coordinador falla")
        assert proc_conn.execute("SELECT COUNT(*) FROM purchase_orders").fetchone()[0] == 0

    def test_money_rejects_non_finite_and_mixed_currencies(self):
        with pytest.raises(InvalidMoneyError):
            Money("Infinity")
        with pytest.raises(InvalidMoneyError):
            Money("10", "MXN").add(Money("10", "USD"))
