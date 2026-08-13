"""Customer360QueryService (§27-29, §57) — the single "expediente" view:
composes every other query service this pipeline has built into one DTO.
Reads only; never mutates, and never re-implements a query another
service already owns — this class is pure composition.

Graceful degradation: only the core profile fetch is a hard gate — if the
caller can't see the customer at all (``CustomerScopeError``/
``CustomerNotFoundError``), the whole call fails, matching every other
query service's behavior. Every *other* section (credit, consent,
ownership, portfolio, segments/tags, pipeline, cases, activities, tasks,
duplicates, quality issues, history) is independently permission-gated by
its own underlying service, and a caller who lacks that section's specific
permission gets ``None``/``[]`` for that field instead of the whole 360
view failing — the same "some tabs are visible, some aren't" experience a
real Customer 360 screen needs, since no single role in §59-61's suggested
matrix holds every one of these permissions at once.

Composes (does not duplicate): CustomerProfileQueryService (CRM-3),
CustomerCreditQueryService (CRM-8), CustomerConsentQueryService (CRM-9),
CustomerOwnershipQueryService/CustomerPortfolioQueryService/
CustomerSegmentationQueryService (CRM-10), CustomerDuplicateQueryService/
CustomerDataQualityQueryService (CRM-11), OpportunityDirectoryQueryService/
CRMActivityQueryService/CRMTaskQueryService (CRM-5/6, extended this phase
with ``list_for_customer``), ServiceCaseQueryService (CRM-7, extended this
phase), CustomerHistoryQueryService (CRM-12).

CRM-13 (§49-55) additionally composes CustomerOrdersSummaryQuery/
CustomerDeliverySummaryQuery/CustomerWhatsAppSummaryQuery/
LoyaltyCustomerSummaryQuery — each degrades the same way (``_safe``) as
every other section here, which for these four means every field usually
comes back empty today: see ``backend.application.customers.integrations.
sales_event_handlers`` for the documented cross-context identity gap that
makes that the *correct* result right now, not a bug in this file.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.application.crm.authorization import CRMAuthorizationPolicy
from backend.application.crm.data_scope import CRMDataScopeResolver, CRMScopeContext
from backend.application.crm.queries.crm_activity_query_service import CRMActivityQueryService
from backend.application.crm.queries.crm_task_query_service import CRMTaskQueryService
from backend.application.crm.queries.customer_ownership_query_service import (
    CustomerOwnershipQueryService,
)
from backend.application.crm.queries.customer_portfolio_query_service import (
    CustomerPortfolioQueryService,
)
from backend.application.crm.queries.customer_segmentation_query_service import (
    CustomerSegmentationQueryService,
)
from backend.application.crm.queries.opportunity_directory_query_service import (
    OpportunityDirectoryQueryService,
)
from backend.application.customer_credit.queries.customer_credit_query_service import (
    CustomerCreditQueryService,
    CustomerCreditSummaryView,
)
from backend.application.customer_privacy.queries.customer_consent_query_service import (
    CustomerConsentQueryService,
)
from backend.application.customer_service.queries.service_case_query_service import (
    ServiceCaseQueryService,
)
from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.customers.data_scope import CustomerDataScopeResolver, CustomerScopeContext
from backend.application.customers.queries.customer_data_quality_query_service import (
    CustomerDataQualityQueryService,
)
from backend.application.customers.queries.customer_delivery_summary_query import (
    CustomerDeliverySummaryQuery,
)
from backend.application.customers.queries.customer_duplicate_query_service import (
    CustomerDuplicateQueryService,
)
from backend.application.customers.queries.customer_history_query_service import (
    CustomerHistoryQueryService,
    CustomerTimelineEntry,
)
from backend.application.customers.queries.customer_orders_summary_query import (
    CustomerOrdersSummaryQuery,
)
from backend.application.customers.queries.customer_profile_query_service import (
    CustomerProfile,
    CustomerProfileQueryService,
)
from backend.application.customers.queries.customer_whatsapp_summary_query import (
    CustomerWhatsAppSummaryQuery,
)
from backend.application.customers.queries.loyalty_customer_summary_query import (
    LoyaltyCustomerSummaryQuery,
)
from backend.domain.crm.exceptions import CRMDomainError
from backend.domain.customer_privacy.exceptions import CustomerPrivacyDomainError
from backend.domain.customers.exceptions import CustomerDomainError


@dataclass(frozen=True)
class Customer360View:
    profile: CustomerProfile
    credit_summary: CustomerCreditSummaryView | None = None
    active_consents: list = field(default_factory=list)
    ownership_by_type: dict = field(default_factory=dict)
    current_portfolio: object | None = None
    active_segments: list = field(default_factory=list)
    active_tags: list = field(default_factory=list)
    open_opportunities: list = field(default_factory=list)
    open_cases: list = field(default_factory=list)
    recent_activities: list = field(default_factory=list)
    pending_tasks: list = field(default_factory=list)
    open_duplicate_candidates: list = field(default_factory=list)
    open_quality_issues: list = field(default_factory=list)
    recent_history: list[CustomerTimelineEntry] = field(default_factory=list)
    orders_summary: object | None = None
    delivery_summary: object | None = None
    whatsapp_summary: object | None = None
    loyalty_summary: object | None = None


class Customer360QueryService:
    def __init__(
        self, connection, customer_scope_resolver: CustomerDataScopeResolver,
        crm_scope_resolver: CRMDataScopeResolver,
        customer_authorization: CustomerAuthorizationPolicy | None = None,
        crm_authorization: CRMAuthorizationPolicy | None = None,
    ) -> None:
        self._connection = connection
        self._customer_scope_resolver = customer_scope_resolver
        self._crm_scope_resolver = crm_scope_resolver
        self._customer_auth = customer_authorization or CustomerAuthorizationPolicy()
        self._crm_auth = crm_authorization or CRMAuthorizationPolicy()

    def get_360(
        self, customer_id: str, *, actor_user_id: str, team_member_ids: tuple[str, ...] = (),
        branch_id: str | None = None, territory_id: str | None = None,
        portfolio_id: str | None = None, history_limit: int = 50,
    ) -> Customer360View:
        customer_context = CustomerScopeContext(
            user_id=actor_user_id, branch_id=branch_id, territory_id=territory_id,
            portfolio_id=portfolio_id, team_member_ids=team_member_ids)
        crm_context = CRMScopeContext(user_id=actor_user_id, team_member_ids=team_member_ids)

        # Hard gate: no profile access, no 360 view.
        profile = CustomerProfileQueryService(
            self._connection, self._customer_scope_resolver,
        ).get_profile(customer_id, customer_context)

        return Customer360View(
            profile=profile,
            credit_summary=self._safe(
                lambda: CustomerCreditQueryService(self._connection, self._customer_auth)
                .get_summary(customer_id, actor_user_id=actor_user_id)),
            active_consents=self._safe(
                lambda: CustomerConsentQueryService(self._connection, self._customer_auth)
                .list_for_customer(customer_id, actor_user_id=actor_user_id), default=[]),
            ownership_by_type=self._safe(
                lambda: CustomerOwnershipQueryService(self._connection, self._crm_auth)
                .get_current_by_type(customer_id, actor_user_id=actor_user_id), default={}),
            current_portfolio=self._safe(
                lambda: CustomerPortfolioQueryService(self._connection, self._crm_auth)
                .get_current_portfolio(customer_id, actor_user_id=actor_user_id)),
            active_segments=self._safe(
                lambda: CustomerSegmentationQueryService(self._connection, self._crm_auth)
                .list_active_memberships(customer_id, actor_user_id=actor_user_id), default=[]),
            active_tags=self._safe(
                lambda: CustomerSegmentationQueryService(self._connection, self._crm_auth)
                .list_active_tag_assignments(customer_id, actor_user_id=actor_user_id),
                default=[]),
            open_opportunities=self._safe(
                lambda: OpportunityDirectoryQueryService(self._connection, self._crm_scope_resolver)
                .list_for_customer(customer_id, crm_context), default=[]),
            open_cases=self._safe(
                lambda: ServiceCaseQueryService(
                    self._connection, self._crm_scope_resolver, self._crm_auth)
                .list_for_customer(customer_id, crm_context), default=[]),
            recent_activities=self._safe(
                lambda: CRMActivityQueryService(self._connection, self._crm_auth)
                .list_for_related_entity("CUSTOMER", customer_id, actor_user_id=actor_user_id),
                default=[]),
            pending_tasks=self._safe(
                lambda: CRMTaskQueryService(self._connection, self._crm_auth)
                .list_for_related_entity("CUSTOMER", customer_id, actor_user_id=actor_user_id),
                default=[]),
            open_duplicate_candidates=self._safe(
                lambda: [c for c in CustomerDuplicateQueryService(
                    self._connection, self._customer_auth)
                    .list_for_customer(customer_id, actor_user_id=actor_user_id)
                    if c.status.value not in ("DISMISSED", "MERGED")], default=[]),
            open_quality_issues=self._safe(
                lambda: CustomerDataQualityQueryService(self._connection, self._customer_auth)
                .list_open_for_customer(customer_id, actor_user_id=actor_user_id), default=[]),
            recent_history=self._safe(
                lambda: CustomerHistoryQueryService(self._connection, self._customer_auth)
                .get_timeline(customer_id, actor_user_id=actor_user_id, limit=history_limit),
                default=[]),
            orders_summary=self._safe(
                lambda: CustomerOrdersSummaryQuery(self._connection, self._customer_auth)
                .get_summary(customer_id, actor_user_id=actor_user_id)),
            delivery_summary=self._safe(
                lambda: CustomerDeliverySummaryQuery(self._connection, self._customer_auth)
                .get_summary(customer_id, actor_user_id=actor_user_id)),
            whatsapp_summary=self._safe(
                lambda: CustomerWhatsAppSummaryQuery(self._connection, self._customer_auth)
                .get_summary(customer_id, actor_user_id=actor_user_id)),
            loyalty_summary=self._safe(
                lambda: LoyaltyCustomerSummaryQuery(self._connection, self._customer_auth)
                .get_summary(customer_id, actor_user_id=actor_user_id)),
        )

    @staticmethod
    def _safe(getter, *, default=None):
        try:
            return getter()
        except (CustomerDomainError, CRMDomainError, CustomerPrivacyDomainError):
            return default
