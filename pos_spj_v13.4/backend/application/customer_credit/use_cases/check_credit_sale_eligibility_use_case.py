"""CheckCreditSaleEligibilityUseCase (§38) — the read-only gate Ventas/POS
calls before booking a credit sale. "Nunca autorizar crédito directo desde
POS" — this bounded context never initiates a sale; it only answers
whether one would be eligible, with every violated rule listed (never a
bare yes/no).

Computes ``available_credit`` from ``CustomerAccountsReceivableSummaryQuery``
(live, read-only against Finanzas' own CxC tables) rather than trusting a
stored value — see that query's docstring for why nothing here ever
persists exposure.
"""

from __future__ import annotations

from decimal import Decimal

from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.customers.permissions import CustomerPermissions
from backend.application.customer_credit.queries.customer_accounts_receivable_summary_query import (
    CustomerAccountsReceivableSummaryQuery,
)
from backend.application.customer_credit.result import CustomerCreditResult
from backend.domain.customer_credit.policies.credit_sale_eligibility_policy import (
    CreditSaleEligibilityPolicy,
)
from backend.domain.customers.exceptions import CustomerDomainError
from backend.infrastructure.db.repositories.customer_credit.unit_of_work import (
    CustomerCreditUnitOfWork,
)


class CheckCreditSaleEligibilityUseCase:
    def __init__(self, authorization: CustomerAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or CustomerAuthorizationPolicy()
        self._policy = CreditSaleEligibilityPolicy()

    def execute(
        self, connection, *, actor_user_id: str, customer_id: str, amount, operation_id: str,
        is_public_customer: bool = False, documents_current: bool = True,
        branch_allowed: bool = True,
    ) -> CustomerCreditResult:
        try:
            self._auth.require(actor_user_id, CustomerPermissions.CREDIT_VIEW)
        except CustomerDomainError as exc:
            return CustomerCreditResult.fail(str(exc), "PERMISSION_DENIED",
                                             operation_id=operation_id)
        uow = CustomerCreditUnitOfWork(connection)
        profile = uow.profiles.get_by_customer_id(customer_id)
        summary_query = CustomerAccountsReceivableSummaryQuery(connection)
        summary = summary_query.get_summary(
            customer_id, payment_terms_days=profile.payment_terms_days if profile else 0)
        available_credit = (
            (profile.credit_limit - summary.current_exposure) if profile else Decimal("0"))
        result = self._policy.evaluate(
            profile, amount=Decimal(str(amount)), is_public_customer=is_public_customer,
            available_credit=available_credit, documents_current=documents_current,
            branch_allowed=branch_allowed)
        if result.eligible:
            return CustomerCreditResult.ok(
                "Venta a crédito elegible", operation_id=operation_id,
                available_credit=str(available_credit))
        return CustomerCreditResult.fail(
            "Venta a crédito no elegible", "NOT_ELIGIBLE", operation_id=operation_id,
            violations=list(result.violations))
