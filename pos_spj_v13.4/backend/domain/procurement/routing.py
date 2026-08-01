"""Explicit, configuration-driven purchase routing policy."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.domain.procurement.enums import (
    PaymentCondition,
    PurchaseNature,
    PurchaseRoutingDecision,
)


@dataclass(frozen=True, slots=True)
class PurchaseRoutingContext:
    nature: PurchaseNature
    amount: Decimal
    urgent: bool
    branch_id: str
    user_id: str
    payment_condition: PaymentCondition
    supplier_id: str | None = None
    category_id: str | None = None
    has_contract: bool = False
    budget_available: bool = True
    quotations_required: bool = False
    direct_permission: bool = False
    direct_limit: Decimal | None = None
    authorization_limit: Decimal | None = None
    approved_requisition_id: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.amount, float):
            raise TypeError("Routing amount must be Decimal")


class PurchaseRoutingPolicy:
    """Return one auditable routing decision; never infer workflow in the UI."""

    def evaluate(self, context: PurchaseRoutingContext) -> PurchaseRoutingDecision:
        if not context.user_id or not context.branch_id or context.amount <= 0:
            return PurchaseRoutingDecision.BLOCKED
        if not context.budget_available and not context.urgent:
            return PurchaseRoutingDecision.BLOCKED
        if context.quotations_required:
            return PurchaseRoutingDecision.RFQ_REQUIRED
        if context.nature is PurchaseNature.ASSET:
            return PurchaseRoutingDecision.PURCHASE_ORDER_REQUIRED
        if context.has_contract and context.payment_condition is PaymentCondition.SUPPLIER_CREDIT:
            return PurchaseRoutingDecision.PURCHASE_ORDER_REQUIRED
        if not context.direct_permission:
            return PurchaseRoutingDecision.REQUISITION_REQUIRED
        if context.direct_limit is not None and context.amount > context.direct_limit:
            return PurchaseRoutingDecision.REQUISITION_REQUIRED
        if (context.authorization_limit is not None
                and context.amount > context.authorization_limit):
            return PurchaseRoutingDecision.DIRECT_REQUIRES_AUTHORIZATION
        return PurchaseRoutingDecision.DIRECT_ALLOWED
