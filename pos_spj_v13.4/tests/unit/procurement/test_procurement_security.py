"""FASE PUR-2 — procurement security domain tests (limits, workflow, segregation)."""

from datetime import time
from decimal import Decimal

import pytest

from backend.application.procurement.authorization import PurchaseAuthorizationPolicy
from backend.application.procurement.permissions import (
    ALL_PURCHASE_PERMISSIONS,
    PurchasePermissions,
)
from backend.domain.procurement.enums import PurchaseFlow
from backend.domain.procurement.events import (
    ALL_PROCUREMENT_EVENTS,
    ReplenishmentNeedEvents,
    build_event_payload,
)
from backend.domain.procurement.exceptions import (
    AuthorizationRequiredError,
    InvalidMoneyError,
    InvalidPaymentSourceError,
    PurchaseLimitExceededError,
    PurchasePermissionDeniedError,
    SegregationOfDutiesError,
    SupplierNotEligibleError,
    TimeWindowError,
)
from backend.domain.procurement.policies import (
    DirectPurchasePolicy,
    ImmediatePaymentPolicy,
    LimitEvaluation,
    PurchaseWorkflowPolicy,
    SegregationOfDutiesPolicy,
    TimeWindowPolicy,
    UserPurchaseLimitPolicy,
)
from backend.domain.procurement.value_objects import (
    Money,
    PurchaseLimit,
    ReceivingWindow,
)


def _limit(cap="5000", approval_above="2000"):
    return PurchaseLimit(maximum_per_transaction=Decimal(cap),
                         requires_approval_above=Decimal(approval_above))


class TestMoney:
    def test_rejects_float(self):
        with pytest.raises(InvalidMoneyError):
            Money(10.5)
        assert Money(Decimal("10.50")).to_string() == "10.50"


class TestUserPurchaseLimit:
    def test_within(self):
        assert UserPurchaseLimitPolicy().evaluate(Money(Decimal("1500")), _limit()) \
            is LimitEvaluation.WITHIN

    def test_requires_approval(self):
        assert UserPurchaseLimitPolicy().evaluate(Money(Decimal("3000")), _limit()) \
            is LimitEvaluation.REQUIRES_APPROVAL

    def test_exceeds(self):
        assert UserPurchaseLimitPolicy().evaluate(Money(Decimal("9000")), _limit()) \
            is LimitEvaluation.EXCEEDS

    def test_no_limit_is_within(self):
        assert UserPurchaseLimitPolicy().evaluate(Money(Decimal("1")), None) \
            is LimitEvaluation.WITHIN

    def test_enforce_direct_raises(self):
        pol = UserPurchaseLimitPolicy()
        with pytest.raises(AuthorizationRequiredError):
            pol.enforce_direct_execution(Money(Decimal("3000")), _limit())
        with pytest.raises(PurchaseLimitExceededError):
            pol.enforce_direct_execution(Money(Decimal("9000")), _limit())


class TestWorkflowSelection:
    def test_direct_flow_within_limit(self):
        flow = PurchaseWorkflowPolicy().select_flow(
            amount=Money(Decimal("800")), user_limit=_limit())
        assert flow is PurchaseFlow.DIRECT_FLOW

    def test_enterprise_when_exceeds(self):
        flow = PurchaseWorkflowPolicy().select_flow(
            amount=Money(Decimal("80000")), user_limit=_limit())
        assert flow is PurchaseFlow.ENTERPRISE_FLOW

    def test_emergency(self):
        flow = PurchaseWorkflowPolicy().select_flow(
            amount=Money(Decimal("500")), is_emergency=True)
        assert flow is PurchaseFlow.EMERGENCY_FLOW

    def test_enterprise_when_quotation_required(self):
        flow = PurchaseWorkflowPolicy().select_flow(
            amount=Money(Decimal("500")), requires_quotation=True)
        assert flow is PurchaseFlow.ENTERPRISE_FLOW


class TestDirectPurchasePolicy:
    def test_happy_path(self):
        DirectPurchasePolicy().enforce_can_execute(
            amount=Money(Decimal("800")), branch_allows_direct=True,
            supplier_active=True, supplier_purchasing_blocked=False, user_limit=_limit())

    def test_branch_disabled(self):
        with pytest.raises(SupplierNotEligibleError):
            DirectPurchasePolicy().enforce_can_execute(
                amount=Money(Decimal("800")), branch_allows_direct=False,
                supplier_active=True, supplier_purchasing_blocked=False, user_limit=_limit())

    def test_blocked_supplier(self):
        with pytest.raises(SupplierNotEligibleError):
            DirectPurchasePolicy().enforce_can_execute(
                amount=Money(Decimal("800")), branch_allows_direct=True,
                supplier_active=True, supplier_purchasing_blocked=True, user_limit=_limit())

    def test_over_limit_escalates(self):
        with pytest.raises((AuthorizationRequiredError, PurchaseLimitExceededError)):
            DirectPurchasePolicy().enforce_can_execute(
                amount=Money(Decimal("9000")), branch_allows_direct=True,
                supplier_active=True, supplier_purchasing_blocked=False, user_limit=_limit())


class TestImmediatePayment:
    def test_pos_cash_forbidden(self):
        with pytest.raises(InvalidPaymentSourceError):
            ImmediatePaymentPolicy().enforce_source("POS_CASH")

    def test_valid_treasury(self):
        ImmediatePaymentPolicy().enforce_source("TREASURY_ACCOUNT")

    def test_not_in_allowed(self):
        with pytest.raises(InvalidPaymentSourceError):
            ImmediatePaymentPolicy().enforce_source(
                "BANK_TRANSFER", allowed_sources={"PETTY_CASH"})


class TestTimeWindow:
    def test_within(self):
        window = ReceivingWindow(time(6, 0), time(20, 0))
        TimeWindowPolicy().enforce_within_window(time(10, 0), window)

    def test_outside(self):
        window = ReceivingWindow(time(6, 0), time(20, 0))
        with pytest.raises(TimeWindowError):
            TimeWindowPolicy().enforce_within_window(time(23, 0), window)


class TestSegregation:
    def test_requester_cannot_self_approve_above_limit(self):
        with pytest.raises(SegregationOfDutiesError):
            SegregationOfDutiesPolicy().enforce_requester_not_self_approving_above_limit(
                "u1", "u1", within_limit=False)

    def test_within_limit_self_ok(self):
        SegregationOfDutiesPolicy().enforce_requester_not_self_approving_above_limit(
            "u1", "u1", within_limit=True)  # no raise

    def test_receiver_not_price_changer(self):
        with pytest.raises(SegregationOfDutiesError):
            SegregationOfDutiesPolicy().enforce_receiver_not_price_changer("u1", "u1")

    def test_payment_requester_not_executor(self):
        with pytest.raises(SegregationOfDutiesError):
            SegregationOfDutiesPolicy().enforce_payment_requester_not_executor("u1", "u1")
        SegregationOfDutiesPolicy().enforce_payment_requester_not_executor("u1", "u2")


class TestAuthorization:
    def test_unknown_permission(self):
        with pytest.raises(PurchasePermissionDeniedError):
            PurchaseAuthorizationPolicy().require("u1", "PURCHASES_NOPE")

    def test_no_checker_allows(self):
        PurchaseAuthorizationPolicy().require("u1", PurchasePermissions.DIRECT_CREATE)

    def test_checker_denies(self):
        class Deny:
            def has_permission(self, u, p):
                return False
        with pytest.raises(PurchasePermissionDeniedError):
            PurchaseAuthorizationPolicy(Deny()).require("u1", PurchasePermissions.DIRECT_CREATE)

    def test_hot_authorization_requires_authorizer(self):
        with pytest.raises(PurchasePermissionDeniedError):
            PurchaseAuthorizationPolicy().authorize_exception("", PurchasePermissions.DIRECT_CONFIRM)

    def test_permission_catalog_is_granular(self):
        # a broad "PURCHASES_ALL" must not exist; codes are per-action
        assert "PURCHASES_ALL" not in ALL_PURCHASE_PERMISSIONS
        assert len(ALL_PURCHASE_PERMISSIONS) >= 60


class TestEvents:
    def test_replenishment_need_events_exist(self):
        for e in (ReplenishmentNeedEvents.PURCHASE_NEED_DETECTED,
                  ReplenishmentNeedEvents.STOCK_REPLENISHMENT_REQUIRED,
                  ReplenishmentNeedEvents.PURCHASE_REQUISITION_REQUESTED,
                  ReplenishmentNeedEvents.CUSTOMER_ORDER_REQUIRES_PURCHASE):
            assert e in ALL_PROCUREMENT_EVENTS

    def test_payload_has_minimum_fields(self):
        p = build_event_payload(
            ReplenishmentNeedEvents.STOCK_REPLENISHMENT_REQUIRED, operation_id="op",
            document_id="d1", source_channel="POS_REPLENISHMENT_REQUEST",
            branch_id="b1", user_id="u1")
        for key in ("event_id", "operation_id", "document_id", "source_channel",
                    "branch_id", "user_id", "timestamp", "source_module"):
            assert key in p
        assert p["event_id"] != p["operation_id"]
