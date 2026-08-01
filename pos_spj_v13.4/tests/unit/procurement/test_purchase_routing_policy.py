from decimal import Decimal

import pytest

from backend.domain.procurement.enums import (
    PaymentCondition, PurchaseNature, PurchaseRoutingDecision,
)
from backend.domain.procurement.routing import PurchaseRoutingContext, PurchaseRoutingPolicy
from backend.domain.procurement.entities import QuoteComparison, SupplierQuote, SupplierQuoteLine
from backend.domain.procurement.value_objects import Money


def context(**changes):
    values = dict(
        nature=PurchaseNature.INVENTORY, amount=Decimal("100"), urgent=False,
        branch_id="branch", user_id="user",
        payment_condition=PaymentCondition.IMMEDIATE_PAYMENT,
        direct_permission=True, direct_limit=Decimal("1000"),
        authorization_limit=Decimal("500"),
    )
    values.update(changes)
    return PurchaseRoutingContext(**values)


@pytest.mark.parametrize(("changes", "expected"), [
    ({}, PurchaseRoutingDecision.DIRECT_ALLOWED),
    ({"amount": Decimal("700")}, PurchaseRoutingDecision.DIRECT_REQUIRES_AUTHORIZATION),
    ({"amount": Decimal("2000")}, PurchaseRoutingDecision.REQUISITION_REQUIRED),
    ({"quotations_required": True}, PurchaseRoutingDecision.RFQ_REQUIRED),
    ({"nature": PurchaseNature.ASSET}, PurchaseRoutingDecision.PURCHASE_ORDER_REQUIRED),
    ({"direct_permission": False}, PurchaseRoutingDecision.REQUISITION_REQUIRED),
    ({"budget_available": False}, PurchaseRoutingDecision.BLOCKED),
])
def test_routing_decisions_are_explicit(changes, expected):
    assert PurchaseRoutingPolicy().evaluate(context(**changes)) is expected


def test_routing_rejects_float_amounts():
    with pytest.raises(TypeError):
        context(amount=10.5)


def test_quote_comparison_ranks_by_price_then_lead_time():
    expensive = SupplierQuote.create("rfq", "supplier-b", lead_time_days=1)
    expensive.lines.append(SupplierQuoteLine.create("product", "1", Money("12")))
    cheap = SupplierQuote.create("rfq", "supplier-a", lead_time_days=4)
    cheap.lines.append(SupplierQuoteLine.create("product", "1", Money("10")))
    ranked = QuoteComparison.build("rfq", [expensive, cheap]).ranked_for_product("product")
    assert [entry.supplier_id for entry in ranked] == ["supplier-a", "supplier-b"]
