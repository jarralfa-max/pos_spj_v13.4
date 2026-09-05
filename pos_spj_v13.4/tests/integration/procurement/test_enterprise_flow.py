"""PUR-6..10 — enterprise flow: requisition → PO (versioned) → receipt → invoice
(3-way) with permissions, segregation of duties, atomicity and post-commit events."""

from decimal import Decimal

from backend.application.procurement.authorization import PurchaseAuthorizationPolicy
from backend.application.procurement.permissions import PurchasePermissions
from backend.application.procurement.use_cases.purchase_order_use_cases import (
    ApprovePurchaseOrderUseCase,
    ChangePurchaseOrderUseCase,
    CreatePurchaseOrderUseCase,
    ReceivePurchaseOrderUseCase,
    ReverseGoodsReceiptUseCase,
    SendPurchaseOrderUseCase,
)
from backend.application.procurement.use_cases.quotation_use_cases import (
    AwardSupplierQuoteUseCase,
    CaptureSupplierQuoteUseCase,
    CreateRfqUseCase,
)
from backend.application.procurement.use_cases.requisition_use_cases import (
    ApprovePurchaseRequisitionUseCase,
    CreatePurchaseRequisitionUseCase,
    SubmitPurchaseRequisitionUseCase,
)
from backend.application.procurement.use_cases.supplier_invoice_use_cases import (
    CaptureSupplierInvoiceUseCase,
    MatchSupplierInvoiceUseCase,
    ReleaseInvoiceVarianceUseCase,
)
from backend.application.procurement.queries.enterprise_read_services import (
    InvoiceReadService, ReceiptReadService,
)
from backend.domain.procurement.enums import PurchaseOrderStatus, RequisitionStatus
from backend.domain.procurement.value_objects import Tolerance
from backend.infrastructure.db.repositories.procurement.unit_of_work import (
    ProcurementUnitOfWork,
)


def _pending(conn):
    with ProcurementUnitOfWork(conn) as uow:
        return {r["event_name"] for r in uow.outbox.list_pending(100)}


def test_e2e_requisition_to_single_finance_handoff(proc_conn):
    """One executable acceptance path across every Procurement document boundary."""
    requisition = CreatePurchaseRequisitionUseCase().execute(
        proc_conn, actor_user_id="requester", operation_id="e2e-pr-create",
        branch_id="br-1", purchase_type="INVENTORY",
        lines=[{"product_id": "p-e2e", "quantity": "3"}],
    )
    assert requisition.success
    assert SubmitPurchaseRequisitionUseCase().execute(
        proc_conn, actor_user_id="requester", requisition_id=requisition.entity_id,
        operation_id="e2e-pr-submit").success
    assert ApprovePurchaseRequisitionUseCase().execute(
        proc_conn, approver_user_id="approver", requisition_id=requisition.entity_id,
        operation_id="e2e-pr-approve").success

    order = CreatePurchaseOrderUseCase().execute(
        proc_conn, actor_user_id="buyer", operation_id="e2e-po-create",
        supplier_id="sup-e2e", branch_id="br-1", warehouse_id="wh-1",
        requisition_id=requisition.entity_id,
        lines=[{"product_id": "p-e2e", "description": "Producto E2E",
                "quantity": "3", "unit_price": "25"}],
    )
    assert order.success
    assert ApprovePurchaseOrderUseCase().execute(
        proc_conn, approver_user_id="approver", purchase_order_id=order.entity_id,
        operation_id="e2e-po-approve").success
    assert SendPurchaseOrderUseCase().execute(
        proc_conn, actor_user_id="buyer", purchase_order_id=order.entity_id,
        operation_id="e2e-po-send").success
    assert ReceivePurchaseOrderUseCase().execute(
        proc_conn, actor_user_id="receiver", purchase_order_id=order.entity_id,
        operation_id="e2e-receipt",
        receipt_lines=[{"product_id": "p-e2e", "received_quantity": "3",
                        "accepted_quantity": "3"}]).success

    order_line_id = proc_conn.execute(
        "SELECT id FROM purchase_order_lines WHERE purchase_order_id=?",
        (order.entity_id,)).fetchone()[0]
    invoice = CaptureSupplierInvoiceUseCase().execute(
        proc_conn, actor_user_id="payables", operation_id="e2e-invoice",
        supplier_id="sup-e2e", invoice_number="E2E-001", total="75",
        purchase_order_id=order.entity_id,
        lines=[{"product_id": "p-e2e", "invoiced_quantity": "3",
                "unit_price": "25", "purchase_order_line_id": order_line_id}],
    )
    assert invoice.success
    match = MatchSupplierInvoiceUseCase().execute(
        proc_conn, actor_user_id="payables", operation_id="e2e-match",
        invoice_id=invoice.entity_id)
    assert match.success and match.data["match_result"] == "MATCHED"

    assert proc_conn.execute(
        "SELECT COUNT(*) FROM procurement_outbox "
        "WHERE event_name='ACCOUNT_PAYABLE_CREATE_REQUESTED' "
        "AND deduplication_key=?",
        (f"SUPPLIER_INVOICE:{invoice.entity_id}",),
    ).fetchone()[0] == 1


# ── requisition ──────────────────────────────────────────────────────────────
def test_requisition_create_submit_approve_segregation(proc_conn):
    created = CreatePurchaseRequisitionUseCase().execute(
        proc_conn, actor_user_id="u1", operation_id="rq-1", branch_id="br-1",
        purchase_type="INVENTORY", lines=[{"product_id": "p1", "quantity": "10"}])
    assert created.success
    SubmitPurchaseRequisitionUseCase().execute(
        proc_conn, actor_user_id="u1", requisition_id=created.entity_id, operation_id="rq-s")
    # requester cannot approve their own requisition
    self_ap = ApprovePurchaseRequisitionUseCase().execute(
        proc_conn, approver_user_id="u1", requisition_id=created.entity_id, operation_id="rq-a")
    assert not self_ap.success and self_ap.error_code == "SEGREGATION"
    ok = ApprovePurchaseRequisitionUseCase().execute(
        proc_conn, approver_user_id="jefe", requisition_id=created.entity_id, operation_id="rq-a2")
    assert ok.success and ok.data["status"] == RequisitionStatus.APPROVED.value


# ── purchase order ───────────────────────────────────────────────────────────
def _make_order(conn, op="oc-1"):
    return CreatePurchaseOrderUseCase().execute(
        conn, actor_user_id="u1", operation_id=op, supplier_id="sup-1", branch_id="br-1",
        warehouse_id="wh-1",
        lines=[{"product_id": "p1", "description": "x", "quantity": "10", "unit_price": "100"}])


def test_order_persists_payment_terms(proc_conn):
    created = CreatePurchaseOrderUseCase().execute(
        proc_conn, actor_user_id="u1", operation_id="oc-terms", supplier_id="sup-1",
        branch_id="br-1", warehouse_id="wh-1", payment_terms="NET_30",
        lines=[{"product_id": "p1", "description": "x", "quantity": "1", "unit_price": "1"}])
    assert created.success
    with ProcurementUnitOfWork(proc_conn) as uow:
        po = uow.orders.get(created.entity_id)
        assert po.payment_terms == "NET_30"


def test_order_without_payment_terms_defaults_to_none(proc_conn):
    created = _make_order(proc_conn, op="oc-no-terms")
    with ProcurementUnitOfWork(proc_conn) as uow:
        assert uow.orders.get(created.entity_id).payment_terms is None


def test_order_create_approve_send_receive_inventory(proc_conn):
    created = _make_order(proc_conn)
    assert created.data["total"] == "1000.00"
    # creator cannot self-approve
    self_ap = ApprovePurchaseOrderUseCase().execute(
        proc_conn, approver_user_id="u1", purchase_order_id=created.entity_id, operation_id="a1")
    assert not self_ap.success and self_ap.error_code == "SEGREGATION"
    ApprovePurchaseOrderUseCase().execute(
        proc_conn, approver_user_id="jefe", purchase_order_id=created.entity_id, operation_id="a2")
    SendPurchaseOrderUseCase().execute(
        proc_conn, actor_user_id="u1", purchase_order_id=created.entity_id, operation_id="s1")
    recv = ReceivePurchaseOrderUseCase().execute(
        proc_conn, actor_user_id="alm", purchase_order_id=created.entity_id, operation_id="r1",
        receipt_lines=[{"product_id": "p1", "received_quantity": "10", "accepted_quantity": "8"}])
    assert recv.success
    assert recv.data["order_status"] == PurchaseOrderStatus.RECEIVED.value
    assert recv.data["accepted"] == "8"
    assert "GOODS_RECEIPT_COMPLETED" in _pending(proc_conn)


def test_reverse_goods_receipt_reopens_order(proc_conn):
    created = _make_order(proc_conn, op="oc-rev-1")
    ApprovePurchaseOrderUseCase().execute(
        proc_conn, approver_user_id="jefe", purchase_order_id=created.entity_id, operation_id="a")
    SendPurchaseOrderUseCase().execute(
        proc_conn, actor_user_id="u1", purchase_order_id=created.entity_id, operation_id="s")
    recv = ReceivePurchaseOrderUseCase().execute(
        proc_conn, actor_user_id="alm", purchase_order_id=created.entity_id, operation_id="r",
        receipt_lines=[{"product_id": "p1", "received_quantity": "10", "accepted_quantity": "8"}])
    assert recv.data["order_status"] == PurchaseOrderStatus.RECEIVED.value

    reversal = ReverseGoodsReceiptUseCase().execute(
        proc_conn, actor_user_id="jefe", goods_receipt_id=recv.entity_id,
        operation_id="rev-1", reason="captura duplicada")
    assert reversal.success
    assert reversal.data["status"] == "REVERSED"
    assert reversal.data["order_status"] == PurchaseOrderStatus.SENT.value
    assert "GOODS_RECEIPT_REVERSED" in _pending(proc_conn)

    with ProcurementUnitOfWork(proc_conn) as uow:
        po = uow.orders.get(created.entity_id)
        line = po.lines[0]
        assert line.received_quantity == Decimal("0")
        assert line.accepted_quantity == Decimal("0")
        assert line.rejected_quantity == Decimal("0")


def test_reverse_goods_receipt_is_idempotent(proc_conn):
    created = _make_order(proc_conn, op="oc-rev-2")
    ApprovePurchaseOrderUseCase().execute(
        proc_conn, approver_user_id="jefe", purchase_order_id=created.entity_id, operation_id="a")
    SendPurchaseOrderUseCase().execute(
        proc_conn, actor_user_id="u1", purchase_order_id=created.entity_id, operation_id="s")
    recv = ReceivePurchaseOrderUseCase().execute(
        proc_conn, actor_user_id="alm", purchase_order_id=created.entity_id, operation_id="r",
        receipt_lines=[{"product_id": "p1", "received_quantity": "10", "accepted_quantity": "10"}])
    ReverseGoodsReceiptUseCase().execute(
        proc_conn, actor_user_id="jefe", goods_receipt_id=recv.entity_id,
        operation_id="rev-a", reason="motivo")
    second = ReverseGoodsReceiptUseCase().execute(
        proc_conn, actor_user_id="jefe", goods_receipt_id=recv.entity_id,
        operation_id="rev-b", reason="motivo")
    assert second.success
    assert second.data["status"] == "REVERSED"


def test_reverse_goods_receipt_requires_permission(proc_conn):
    created = _make_order(proc_conn, op="oc-rev-3")
    ApprovePurchaseOrderUseCase().execute(
        proc_conn, approver_user_id="jefe", purchase_order_id=created.entity_id, operation_id="a")
    SendPurchaseOrderUseCase().execute(
        proc_conn, actor_user_id="u1", purchase_order_id=created.entity_id, operation_id="s")
    recv = ReceivePurchaseOrderUseCase().execute(
        proc_conn, actor_user_id="alm", purchase_order_id=created.entity_id, operation_id="r",
        receipt_lines=[{"product_id": "p1", "received_quantity": "10", "accepted_quantity": "10"}])
    class NoReverse:
        def has_permission(self, user_id, permission_code):
            return permission_code != PurchasePermissions.RECEIPT_REVERSE

    auth = PurchaseAuthorizationPolicy(NoReverse())
    result = ReverseGoodsReceiptUseCase(auth).execute(
        proc_conn, actor_user_id="jefe", goods_receipt_id=recv.entity_id,
        operation_id="rev-denied", reason="motivo")
    assert not result.success and result.error_code == "PERMISSION_DENIED"


def test_partial_receipt_keeps_order_open(proc_conn):
    created = _make_order(proc_conn, op="oc-2")
    ApprovePurchaseOrderUseCase().execute(
        proc_conn, approver_user_id="jefe", purchase_order_id=created.entity_id, operation_id="a")
    SendPurchaseOrderUseCase().execute(
        proc_conn, actor_user_id="u1", purchase_order_id=created.entity_id, operation_id="s")
    recv = ReceivePurchaseOrderUseCase().execute(
        proc_conn, actor_user_id="alm", purchase_order_id=created.entity_id, operation_id="r",
        receipt_lines=[{"product_id": "p1", "received_quantity": "4", "accepted_quantity": "4"}])
    assert recv.data["order_status"] == PurchaseOrderStatus.PARTIALLY_RECEIVED.value


def test_over_tolerance_receipt_requires_permission(proc_conn):
    created = _make_order(proc_conn, op="oc-3")
    ApprovePurchaseOrderUseCase().execute(
        proc_conn, approver_user_id="jefe", purchase_order_id=created.entity_id, operation_id="a")
    SendPurchaseOrderUseCase().execute(
        proc_conn, actor_user_id="u1", purchase_order_id=created.entity_id, operation_id="s")
    class NoOverReceipt:
        def has_permission(self, user_id, permission_code):
            return permission_code != PurchasePermissions.RECEIPT_OVER_TOLERANCE

    uc = ReceivePurchaseOrderUseCase(
        PurchaseAuthorizationPolicy(NoOverReceipt()),
        tolerance=Tolerance(Decimal("5")))
    blocked = uc.execute(
        proc_conn, actor_user_id="alm", purchase_order_id=created.entity_id, operation_id="r",
        receipt_lines=[{"product_id": "p1", "received_quantity": "20", "accepted_quantity": "20"}],
        has_over_receive_permission=False)
    assert not blocked.success and blocked.error_code == "OVER_TOLERANCE"


def test_receiver_cannot_be_price_changer(proc_conn):
    created = _make_order(proc_conn, op="oc-4")
    ApprovePurchaseOrderUseCase().execute(
        proc_conn, approver_user_id="jefe", purchase_order_id=created.entity_id, operation_id="a")
    SendPurchaseOrderUseCase().execute(
        proc_conn, actor_user_id="u1", purchase_order_id=created.entity_id, operation_id="s")
    blocked = ReceivePurchaseOrderUseCase().execute(
        proc_conn, actor_user_id="alm", purchase_order_id=created.entity_id, operation_id="r",
        receipt_lines=[{"product_id": "p1", "received_quantity": "10", "accepted_quantity": "10"}],
        price_changer_id="alm")
    assert not blocked.success and blocked.error_code == "SEGREGATION"


def test_change_after_approval_bumps_version_and_reopens_approval(proc_conn):
    created = _make_order(proc_conn, op="oc-5")
    ApprovePurchaseOrderUseCase().execute(
        proc_conn, approver_user_id="jefe", purchase_order_id=created.entity_id, operation_id="a")
    SendPurchaseOrderUseCase().execute(
        proc_conn, actor_user_id="u1", purchase_order_id=created.entity_id, operation_id="s")
    changed = ChangePurchaseOrderUseCase().execute(
        proc_conn, actor_user_id="u1", purchase_order_id=created.entity_id, operation_id="c",
        reason="cambio de precio",
        line_changes=[])
    assert changed.success and changed.data["version"] == 2
    assert changed.data["status"] == PurchaseOrderStatus.PENDING_APPROVAL.value
    versions = proc_conn.execute(
        "SELECT COUNT(*) FROM purchase_order_versions WHERE purchase_order_id=?",
        (created.entity_id,)).fetchone()[0]
    assert versions >= 2  # alta + cambio


def test_change_requires_reason(proc_conn):
    created = _make_order(proc_conn, op="oc-6")
    ApprovePurchaseOrderUseCase().execute(
        proc_conn, approver_user_id="jefe", purchase_order_id=created.entity_id, operation_id="a")
    changed = ChangePurchaseOrderUseCase().execute(
        proc_conn, actor_user_id="u1", purchase_order_id=created.entity_id, operation_id="c",
        reason="  ")
    assert not changed.success and changed.error_code == "VALIDATION"


# ── RFQ / quotes ─────────────────────────────────────────────────────────────
def test_rfq_quote_award(proc_conn):
    rfq = CreateRfqUseCase().execute(
        proc_conn, actor_user_id="u1", operation_id="rfq-1", supplier_ids=["s1", "s2"])
    assert rfq.success
    quote = CaptureSupplierQuoteUseCase().execute(
        proc_conn, actor_user_id="u1", operation_id="q-1", rfq_id=rfq.entity_id,
        supplier_id="s1", lead_time_days=3,
        lines=[{"product_id": "p1", "quantity": "10", "unit_price": "90"}])
    assert quote.data["total"] == "900.00"
    award = AwardSupplierQuoteUseCase().execute(
        proc_conn, actor_user_id="u1", operation_id="aw-1", quote_id=quote.entity_id,
        reason="mejor precio")
    assert award.success
    assert proc_conn.execute(
        "SELECT COUNT(*) FROM purchase_award_lines WHERE award_id=?",
        (award.entity_id,)).fetchone()[0] == 1


def test_create_rfq_is_idempotent_by_operation_id(proc_conn):
    """A retried CreateRfqUseCase call (same operation_id) must return the
    existing RFQ instead of creating a second row and crashing on the
    operation_id UNIQUE constraint."""
    first = CreateRfqUseCase().execute(
        proc_conn, actor_user_id="u1", operation_id="rfq-retry", supplier_ids=["s1"])
    assert first.success
    second = CreateRfqUseCase().execute(
        proc_conn, actor_user_id="u1", operation_id="rfq-retry", supplier_ids=["s1"])
    assert second.success
    assert second.entity_id == first.entity_id
    assert proc_conn.execute(
        "SELECT COUNT(*) FROM requests_for_quotation WHERE operation_id=?",
        ("rfq-retry",)).fetchone()[0] == 1


# ── supplier invoice / 3-way ─────────────────────────────────────────────────
def _received_order(conn, op="oc-inv"):
    created = _make_order(conn, op=op)
    ApprovePurchaseOrderUseCase().execute(
        conn, approver_user_id="jefe", purchase_order_id=created.entity_id, operation_id=op + "-a")
    SendPurchaseOrderUseCase().execute(
        conn, actor_user_id="u1", purchase_order_id=created.entity_id, operation_id=op + "-s")
    ReceivePurchaseOrderUseCase().execute(
        conn, actor_user_id="alm", purchase_order_id=created.entity_id, operation_id=op + "-r",
        receipt_lines=[{"product_id": "p1", "received_quantity": "10", "accepted_quantity": "10"}])
    return created.entity_id


def test_invoice_capture_match_creates_payable(proc_conn):
    po_id = _received_order(proc_conn)
    po_line_id = proc_conn.execute(
        "SELECT id FROM purchase_order_lines WHERE purchase_order_id=?", (po_id,)).fetchone()[0]
    inv = CaptureSupplierInvoiceUseCase().execute(
        proc_conn, actor_user_id="cxp", operation_id="inv-1", supplier_id="sup-1",
        invoice_number="A-100", total="1000", purchase_order_id=po_id,
        lines=[{"product_id": "p1", "invoiced_quantity": "10", "unit_price": "100",
                "purchase_order_line_id": po_line_id}])
    assert inv.success
    matched = MatchSupplierInvoiceUseCase().execute(
        proc_conn, actor_user_id="cxp", operation_id="m-1", invoice_id=inv.entity_id)
    assert matched.data["match_result"] == "MATCHED"
    assert "ACCOUNT_PAYABLE_CREATE_REQUESTED" in _pending(proc_conn)
    repeated = MatchSupplierInvoiceUseCase().execute(
        proc_conn, actor_user_id="cxp", operation_id="m-2", invoice_id=inv.entity_id)
    assert repeated.success
    assert proc_conn.execute(
        "SELECT COUNT(*) FROM procurement_outbox WHERE event_name='ACCOUNT_PAYABLE_CREATE_REQUESTED'"
        " AND deduplication_key=?", (f"SUPPLIER_INVOICE:{inv.entity_id}",)).fetchone()[0] == 1
    receipt_scope = proc_conn.execute(
        "SELECT branch_id,warehouse_id FROM goods_receipts WHERE purchase_order_id=?",
        (po_id,)).fetchone()
    receipt_rows = ReceiptReadService(proc_conn).list(
        branch_id=receipt_scope[0], warehouse_id=receipt_scope[1])
    assert receipt_rows[0].accepted == 10 and receipt_rows[0].rejected == 0
    invoice_detail = InvoiceReadService(proc_conn).detail(inv.entity_id)
    assert invoice_detail.lines[0].invoiced_quantity == "10"
    assert invoice_detail.comparison[0]["accepted_quantity"] == 10


def test_invoice_without_completed_receipt_is_blocked(proc_conn):
    po = _make_order(proc_conn, op="oc-no-receipt")
    line_id = proc_conn.execute(
        "SELECT id FROM purchase_order_lines WHERE purchase_order_id=?", (po.entity_id,)).fetchone()[0]
    inv = CaptureSupplierInvoiceUseCase().execute(
        proc_conn, actor_user_id="cxp", operation_id="inv-no-receipt",
        supplier_id="sup-1", invoice_number="NO-R-1", total="1000",
        purchase_order_id=po.entity_id,
        lines=[{"product_id": "p1", "invoiced_quantity": "10", "unit_price": "100",
                "purchase_order_line_id": line_id}])
    matched = MatchSupplierInvoiceUseCase().execute(
        proc_conn, actor_user_id="cxp", operation_id="match-no-receipt", invoice_id=inv.entity_id)
    assert matched.data["match_result"] == "MISSING_RECEIPT"
    assert proc_conn.execute(
        "SELECT COUNT(*) FROM procurement_outbox WHERE event_name='ACCOUNT_PAYABLE_CREATE_REQUESTED'"
        " AND deduplication_key=?", (f"SUPPLIER_INVOICE:{inv.entity_id}",)).fetchone()[0] == 0


def test_duplicate_invoice_blocked(proc_conn):
    po_id = _received_order(proc_conn, op="oc-dup")
    po_line_id = proc_conn.execute(
        "SELECT id FROM purchase_order_lines WHERE purchase_order_id=?", (po_id,)).fetchone()[0]
    lines = [{"product_id": "p1", "invoiced_quantity": "10", "unit_price": "100",
              "purchase_order_line_id": po_line_id}]
    CaptureSupplierInvoiceUseCase().execute(
        proc_conn, actor_user_id="cxp", operation_id="inv-a", supplier_id="sup-1",
        invoice_number="B-1", total="1000", purchase_order_id=po_id, lines=lines)
    dup = CaptureSupplierInvoiceUseCase().execute(
        proc_conn, actor_user_id="cxp", operation_id="inv-b", supplier_id="sup-1",
        invoice_number="B-1", total="1000", purchase_order_id=po_id, lines=lines)
    assert not dup.success and dup.error_code == "DUPLICATE_INVOICE"


def test_price_variance_then_release_requires_segregation(proc_conn):
    po_id = _received_order(proc_conn, op="oc-var")
    po_line_id = proc_conn.execute(
        "SELECT id FROM purchase_order_lines WHERE purchase_order_id=?", (po_id,)).fetchone()[0]
    inv = CaptureSupplierInvoiceUseCase().execute(
        proc_conn, actor_user_id="cxp", operation_id="inv-v", supplier_id="sup-1",
        invoice_number="C-1", total="1200", purchase_order_id=po_id,
        lines=[{"product_id": "p1", "invoiced_quantity": "10", "unit_price": "120",
                "purchase_order_line_id": po_line_id}])
    matched = MatchSupplierInvoiceUseCase().execute(
        proc_conn, actor_user_id="cxp", operation_id="m-v", invoice_id=inv.entity_id)
    assert matched.data["match_result"] == "PRICE_VARIANCE"
    # the capturer cannot release their own variance
    self_rel = ReleaseInvoiceVarianceUseCase().execute(
        proc_conn, releaser_user_id="cxp", operation_id="rel-1", invoice_id=inv.entity_id,
        captured_by_user_id="forged-other-user", reason="ok")
    assert not self_rel.success and self_rel.error_code == "SEGREGATION"
    ok = ReleaseInvoiceVarianceUseCase().execute(
        proc_conn, releaser_user_id="jefe", operation_id="rel-2", invoice_id=inv.entity_id,
        captured_by_user_id="cxp", reason="autorizado")
    assert ok.success and "ACCOUNT_PAYABLE_CREATE_REQUESTED" in _pending(proc_conn)
