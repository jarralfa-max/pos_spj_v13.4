"""PUR-6..10 — enterprise flow: requisition → PO (versioned) → receipt → invoice
(3-way) with permissions, segregation of duties, atomicity and post-commit events."""

from decimal import Decimal

from backend.application.procurement.use_cases.purchase_order_use_cases import (
    ApprovePurchaseOrderUseCase,
    ChangePurchaseOrderUseCase,
    CreatePurchaseOrderUseCase,
    ReceivePurchaseOrderUseCase,
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
from backend.domain.procurement.enums import PurchaseOrderStatus, RequisitionStatus
from backend.domain.procurement.value_objects import Tolerance
from backend.infrastructure.db.repositories.procurement.unit_of_work import (
    ProcurementUnitOfWork,
)


def _pending(conn):
    with ProcurementUnitOfWork(conn) as uow:
        return {r["event_name"] for r in uow.outbox.list_pending(100)}


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
    uc = ReceivePurchaseOrderUseCase(tolerance=Tolerance(Decimal("5")))
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
    assert bool(proc_conn.execute("SELECT awarded FROM supplier_quotes WHERE id=?",
                                  (quote.entity_id,)).fetchone()[0]) is True


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
    inv = CaptureSupplierInvoiceUseCase().execute(
        proc_conn, actor_user_id="cxp", operation_id="inv-1", supplier_id="sup-1",
        invoice_number="A-100", total="1000", purchase_order_id=po_id)
    assert inv.success
    matched = MatchSupplierInvoiceUseCase().execute(
        proc_conn, actor_user_id="cxp", operation_id="m-1", invoice_id=inv.entity_id)
    assert matched.data["match_result"] == "MATCHED"
    assert "PURCHASE_PAYABLE_CREATED" in _pending(proc_conn)


def test_duplicate_invoice_blocked(proc_conn):
    po_id = _received_order(proc_conn, op="oc-dup")
    CaptureSupplierInvoiceUseCase().execute(
        proc_conn, actor_user_id="cxp", operation_id="inv-a", supplier_id="sup-1",
        invoice_number="B-1", total="1000", purchase_order_id=po_id)
    dup = CaptureSupplierInvoiceUseCase().execute(
        proc_conn, actor_user_id="cxp", operation_id="inv-b", supplier_id="sup-1",
        invoice_number="B-1", total="1000", purchase_order_id=po_id)
    assert not dup.success and dup.error_code == "DUPLICATE_INVOICE"


def test_price_variance_then_release_requires_segregation(proc_conn):
    po_id = _received_order(proc_conn, op="oc-var")
    inv = CaptureSupplierInvoiceUseCase().execute(
        proc_conn, actor_user_id="cxp", operation_id="inv-v", supplier_id="sup-1",
        invoice_number="C-1", total="1200", purchase_order_id=po_id)
    matched = MatchSupplierInvoiceUseCase().execute(
        proc_conn, actor_user_id="cxp", operation_id="m-v", invoice_id=inv.entity_id)
    assert matched.data["match_result"] == "PRICE_VARIANCE"
    # the capturer cannot release their own variance
    self_rel = ReleaseInvoiceVarianceUseCase().execute(
        proc_conn, releaser_user_id="cxp", operation_id="rel-1", invoice_id=inv.entity_id,
        captured_by_user_id="cxp", reason="ok")
    assert not self_rel.success and self_rel.error_code == "SEGREGATION"
    ok = ReleaseInvoiceVarianceUseCase().execute(
        proc_conn, releaser_user_id="jefe", operation_id="rel-2", invoice_id=inv.entity_id,
        captured_by_user_id="cxp", reason="autorizado")
    assert ok.success and "PURCHASE_PAYABLE_CREATED" in _pending(proc_conn)
