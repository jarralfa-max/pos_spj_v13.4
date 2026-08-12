"""CustomerCreditQueryService — read side for credit profiles, combined
with a live CxC summary (§27-29's Customer 360 "Crédito" tab; §37-40).
Reads only; never mutates.

No OWN/TEAM scope axis — CRM-2's catalog only defines flat
``CREDIT_VIEW``/``CREDIT_VIEW_SUMMARY``/``CREDIT_VIEW_SENSITIVE``
permissions for credit (no ``ver.propia``/``ver.equipo`` pair), same
flat-permission precedent already applied to Activities/Tasks/Notes
(CRM-6). Reaching a specific customer's credit tab in the UI already
implies the caller could view that customer via
``CustomerDataScopeResolver``.

Amounts are masked via CRM-2's ``FieldVisibility``/``mask()`` (§75 lists
"límite de crédito"/"saldo" as protected fields) — the first real consumer
of that masking machinery for money amounts: ``CREDIT_VIEW`` alone shows
status/risk but masks every amount; ``CREDIT_VIEW_SUMMARY`` reveals amounts
partially (last 4 digits); ``CREDIT_VIEW_SENSITIVE`` reveals them in full.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.customers.permissions import CustomerPermissions
from backend.application.customer_credit.queries.customer_accounts_receivable_summary_query import (
    CustomerAccountsReceivableSummaryQuery,
)
from backend.domain.customer_credit.enums import CreditProfileStatus
from backend.domain.customers.value_objects.field_visibility import FieldVisibility, mask
from backend.infrastructure.db.repositories.customer_credit.unit_of_work import (
    CustomerCreditUnitOfWork,
)


@dataclass(frozen=True)
class CustomerCreditSummaryView:
    customer_id: str
    status: str
    risk_level: str | None
    payment_terms_days: int | None
    credit_limit: str
    available_credit: str
    current_exposure: str
    overdue_amount: str
    next_due_date: date | None
    visibility: FieldVisibility


class CustomerCreditQueryService:
    def __init__(self, connection, authorization: CustomerAuthorizationPolicy | None = None) -> None:
        self._connection = connection
        self._uow = CustomerCreditUnitOfWork(connection)
        self._auth = authorization or CustomerAuthorizationPolicy()

    def get_summary(self, customer_id: str, *, actor_user_id: str) -> CustomerCreditSummaryView:
        self._auth.require(actor_user_id, CustomerPermissions.CREDIT_VIEW)
        visibility = self._resolve_visibility(actor_user_id)

        profile = self._uow.profiles.get_by_customer_id(customer_id)
        status = profile.status.value if profile else CreditProfileStatus.NOT_CONFIGURED.value
        risk_level = profile.risk_level.value if profile else None
        payment_terms_days = profile.payment_terms_days if profile else None
        credit_limit = profile.credit_limit if profile else Decimal("0")

        summary_query = CustomerAccountsReceivableSummaryQuery(self._connection)
        summary = summary_query.get_summary(customer_id, payment_terms_days=payment_terms_days or 0)
        available_credit = credit_limit - summary.current_exposure

        return CustomerCreditSummaryView(
            customer_id=customer_id, status=status, risk_level=risk_level,
            payment_terms_days=payment_terms_days,
            credit_limit=mask(str(credit_limit), visibility),
            available_credit=mask(str(available_credit), visibility),
            current_exposure=mask(str(summary.current_exposure), visibility),
            overdue_amount=mask(str(summary.overdue_amount), visibility),
            next_due_date=summary.next_due_date, visibility=visibility,
        )

    def _resolve_visibility(self, actor_user_id: str) -> FieldVisibility:
        if self._auth.has_permission(actor_user_id, CustomerPermissions.CREDIT_VIEW_SENSITIVE):
            return FieldVisibility.VISIBLE
        if self._auth.has_permission(actor_user_id, CustomerPermissions.CREDIT_VIEW_SUMMARY):
            return FieldVisibility.PARTIALLY_VISIBLE
        return FieldVisibility.MASKED
