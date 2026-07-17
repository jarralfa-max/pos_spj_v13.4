"""FASE PUR-3 — procurement domain entities + receiving/matching/emergency policies."""

from datetime import date
from decimal import Decimal

import pytest

from backend.domain.procurement.entities import (
    DirectPurchase,
    DirectPurchaseLine,
    GoodsReceipt,
    GoodsReceiptLine,
    PurchaseAuthorization,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseRequisition,
    ReceiptDiscrepancy,
    RequisitionLine,
    SupplierInvoice,
)
from backend.domain.procurement.enums import (
    DirectPurchaseMode,
    DiscrepancyType,
    DocumentStatus,
    PaymentCondition,
    PurchaseOrderStatus,
    PurchaseType,
    RequisitionStatus,
)
from backend.domain.procurement.exceptions import (
    InvalidPurchaseStateError,
    ProcurementDomainError,
)
from backend.domain.procurement.receiving_matching_policies import (
    DuplicatePurchasePolicy,
    EmergencyPurchasePolicy,
    InvoiceMatchingPolicy,
    MatchResult,
    ReceiptTolerancePolicy,
    ToleranceOutcome,
)
from backend.domain.procurement.value_objects import DocumentNumber, Money, Tolerance


def _money(v):
    return Money(Decimal(v))


def _direct(mode=DirectPurchaseMode.DIRECT_WITH_IMMEDIATE_RECEIPT):
    return DirectPurchase.create(
        DocumentNumber("CD", 2026, 1), "sup-1", "br-1", "wh-1", mode,
        PaymentCondition.IMMEDIATE_PAYMENT, created_by_user_id="u1")


class TestDirectPurchase:
    def test_totals_decimal(self):
        dp = _direct()
        dp.add_line(DirectPurchaseLine.create("p1", "Pollo", 3, _money("100"),
                                              tax=_money("48")))
        dp.add_line(DirectPurchaseLine.create("p2", "Caja", 2, _money("50")))
        assert dp.subtotal().amount == Decimal("400")   # 300 + 100
        assert dp.total().amount == Decimal("448.00")   # + 48 tax
        assert isinstance(dp.total().amount, Decimal)

    def test_line_rejects_float(self):
        with pytest.raises(ProcurementDomainError):
            DirectPurchaseLine.create("p1", "x", 1.5, _money("10"))

    def test_conversion_to_inventory_qty(self):
        line = DirectPurchaseLine.create("p1", "Caja", 10, _money("120"),
                                         conversion_factor=Decimal("12"))
        assert line.inventory_quantity() == Decimal("120")

    def test_lifecycle_direct_confirm_receive(self):
        dp = _direct()
        dp.add_line(DirectPurchaseLine.create("p1", "x", 1, _money("10")))
        dp.confirm()
        assert dp.status is DocumentStatus.CONFIRMED
        dp.mark_received()
        assert dp.status is DocumentStatus.RECEIVED

    def test_cannot_confirm_empty(self):
        with pytest.raises(InvalidPurchaseStateError):
            _direct().confirm()

    def test_cannot_modify_after_confirm(self):
        dp = _direct()
        dp.add_line(DirectPurchaseLine.create("p1", "x", 1, _money("10")))
        dp.confirm()
        with pytest.raises(InvalidPurchaseStateError):
            dp.add_line(DirectPurchaseLine.create("p2", "y", 1, _money("5")))

    def test_authorization_flow(self):
        dp = _direct()
        dp.add_line(DirectPurchaseLine.create("p1", "x", 1, _money("9000")))
        dp.request_authorization("supera límite")
        assert dp.status is DocumentStatus.PENDING_AUTHORIZATION
        dp.authorize("u-jefe")
        assert dp.authorized_by_user_id == "u-jefe"
        dp.confirm()
        assert dp.status is DocumentStatus.CONFIRMED

    def test_reverse_requires_confirmed(self):
        dp = _direct()
        dp.add_line(DirectPurchaseLine.create("p1", "x", 1, _money("10")))
        with pytest.raises(InvalidPurchaseStateError):
            dp.reverse()
        dp.confirm()
        dp.reverse()
        assert dp.status is DocumentStatus.REVERSED


class TestRequisition:
    def test_submit_approve(self):
        req = PurchaseRequisition.create(DocumentNumber("SC", 2026, 1), "br-1", "u1",
                                         PurchaseType.INVENTORY)
        req.add_line(RequisitionLine.create("p1", 10))
        req.submit()
        assert req.status is RequisitionStatus.PENDING_APPROVAL
        req.approve("u2")
        assert req.status is RequisitionStatus.APPROVED

    def test_cannot_submit_empty(self):
        req = PurchaseRequisition.create(DocumentNumber("SC", 2026, 2), "br-1", "u1",
                                         PurchaseType.INVENTORY)
        with pytest.raises(InvalidPurchaseStateError):
            req.submit()


class TestPurchaseOrder:
    def _order(self):
        po = PurchaseOrder.create(DocumentNumber("OC", 2026, 1), "sup-1", "br-1", "wh-1",
                                  created_by_user_id="u1")
        po.lines.append(PurchaseOrderLine.create("p1", "x", 10, _money("100")))
        return po

    def test_approve_send_ack(self):
        po = self._order()
        po.submit(); po.approve("u2"); po.send(); po.acknowledge()
        assert po.status is PurchaseOrderStatus.ACKNOWLEDGED
        assert po.total().amount == Decimal("1000.00")

    def test_partial_then_full_receipt(self):
        po = self._order()
        po.submit(); po.approve("u2"); po.send()
        po.register_receipt({po.lines[0].id: Decimal("4")})
        assert po.status is PurchaseOrderStatus.PARTIALLY_RECEIVED
        po.register_receipt({po.lines[0].id: Decimal("6")})
        assert po.status is PurchaseOrderStatus.RECEIVED

    def test_change_after_approval_bumps_version_and_reapproves(self):
        po = self._order()
        po.submit(); po.approve("u2"); po.send()
        po.create_new_version("cambio de precio")
        assert po.version == 2 and po.status is PurchaseOrderStatus.PENDING_APPROVAL

    def test_change_requires_reason(self):
        po = self._order()
        po.submit(); po.approve("u2")
        with pytest.raises(InvalidPurchaseStateError):
            po.create_new_version("  ")


class TestGoodsReceipt:
    def test_only_accepted_enters_inventory(self):
        line = GoodsReceiptLine.create("p1", ordered_quantity=10, received_quantity=10,
                                       accepted_quantity=8)
        assert line.rejected_quantity == Decimal("2")
        assert line.inventory_quantity() == Decimal("8")

    def test_accepted_cannot_exceed_received(self):
        with pytest.raises(ProcurementDomainError):
            GoodsReceiptLine.create("p1", 10, 5, 8)

    def test_receipt_complete_and_discrepancy(self):
        gr = GoodsReceipt.create(DocumentNumber("REC", 2026, 1), "sup-1", "br-1", "wh-1",
                                 received_by_user_id="u1", purchase_order_id="po-1")
        gr.add_line(GoodsReceiptLine.create("p1", 10, 8, 8))
        gr.add_discrepancy(ReceiptDiscrepancy.create(
            DiscrepancyType.SHORT_QUANTITY, 10, 8, "faltante"))
        gr.complete()
        assert gr.status == "COMPLETED" and gr.total_accepted() == Decimal("8")
        assert gr.discrepancies[0].difference() == Decimal("-2")


class TestReceiptTolerance:
    def test_within_and_over(self):
        pol = ReceiptTolerancePolicy()
        tol = Tolerance(Decimal("5"))  # 5%
        assert pol.evaluate_quantity(Decimal("100"), Decimal("103"), tol) is ToleranceOutcome.WITHIN
        assert pol.evaluate_quantity(Decimal("100"), Decimal("120"), tol) is ToleranceOutcome.OVER_TOLERANCE

    def test_over_receipt_needs_authorization(self):
        pol = ReceiptTolerancePolicy()
        with pytest.raises(Exception):
            pol.enforce_over_receipt(Decimal("100"), Decimal("130"), Tolerance(Decimal("5")),
                                     has_override_permission=False)
        pol.enforce_over_receipt(Decimal("100"), Decimal("130"), Tolerance(Decimal("5")),
                                 has_override_permission=True)  # no raise


class TestInvoiceMatching:
    def test_three_way_matched(self):
        result = InvoiceMatchingPolicy().match(
            has_purchase_document=True, has_receipt=True, ordered_total=_money("1000"),
            received_quantity=Decimal("10"), invoiced_quantity=Decimal("10"),
            invoice_total=_money("1000"))
        assert result is MatchResult.MATCHED

    def test_price_variance(self):
        result = InvoiceMatchingPolicy().match(
            has_purchase_document=True, has_receipt=True, ordered_total=_money("1000"),
            received_quantity=Decimal("10"), invoiced_quantity=Decimal("10"),
            invoice_total=_money("1200"))
        assert result is MatchResult.PRICE_VARIANCE

    def test_missing_receipt_and_duplicate(self):
        pol = InvoiceMatchingPolicy()
        assert pol.match(has_purchase_document=True, has_receipt=False, ordered_total=None,
                         received_quantity=None, invoiced_quantity=None,
                         invoice_total=_money("100")) is MatchResult.MISSING_RECEIPT
        assert pol.match(has_purchase_document=True, has_receipt=True, ordered_total=_money("1"),
                         received_quantity=Decimal("1"), invoiced_quantity=Decimal("1"),
                         invoice_total=_money("1"), is_duplicate=True) is MatchResult.DUPLICATE_INVOICE


class TestEmergencyAndDuplicate:
    def test_emergency_requires_justification_and_auth(self):
        pol = EmergencyPurchasePolicy()
        with pytest.raises(ProcurementDomainError):
            pol.enforce(justification="", authorized_by_user_id="u2")
        with pytest.raises(Exception):
            pol.enforce(justification="falla refrigerador", authorized_by_user_id=None)
        pol.enforce(justification="falla refrigerador", authorized_by_user_id="u2")
        assert pol.requires_regularization() is True

    def test_duplicate_invoice_detection(self):
        pol = DuplicatePurchasePolicy()
        existing = [{"supplier_id": "s1", "invoice_number": "A-100"}]
        assert pol.is_duplicate_invoice("s1", "a-100", existing) is True
        assert pol.is_duplicate_invoice("s1", "A-200", existing) is False

    def test_occasional_supplier_registration_alert(self):
        assert DuplicatePurchasePolicy().occasional_supplier_needs_registration(3) is True
        assert DuplicatePurchasePolicy().occasional_supplier_needs_registration(1) is False


class TestSupplierInvoiceAndAuthorization:
    def test_invoice_match_recording(self):
        inv = SupplierInvoice.create(DocumentNumber("FPR", 2026, 1), "s1", "A-100",
                                     _money("1000"), purchase_order_id="po-1")
        inv.record_match("MATCHED")
        assert inv.status == "MATCHED"
        inv2 = SupplierInvoice.create(DocumentNumber("FPR", 2026, 2), "s1", "A-101",
                                      _money("1000"))
        inv2.record_match("PRICE_VARIANCE")
        assert inv2.status == "WITH_DIFFERENCES"

    def test_authorization_record_requires_reason(self):
        with pytest.raises(ProcurementDomainError):
            PurchaseAuthorization.create(
                operation_id="op", permission_code="PURCHASES_DIRECT_CONFIRM",
                requested_by_user_id="u1", authorized_by_user_id="u2", reason="  ",
                amount=_money("9000"))
        auth = PurchaseAuthorization.create(
            operation_id="op", permission_code="PURCHASES_DIRECT_CONFIRM",
            requested_by_user_id="u1", authorized_by_user_id="u2", reason="supera límite",
            amount=_money("9000"))
        assert auth.authorized_by_user_id == "u2"
