"""LoyaltyCustomerSummaryQuery (§49, exact name from master prompt §57):
"CRM muestra programa/nivel/puntos/tarjeta/recompensas resumidas... acciones
detalladas navegan a Fidelidad."

Delegates to Fidelidad's own ``LoyaltyCustomerSummaryQueryService`` — CRM
never reads a Fidelidad table (``tests/architecture/
test_customers_crm_does_not_own_loyalty.py`` forbids them by name).

**LOY-29 (2026-10-02)**: this used to read the legacy ``loyalty_snapshots``
table, which nothing has written since the rebuild — every customer showed
"no inscrito / 0 puntos" in Customer 360 even with a real canonical balance.
``loyalty_snapshots`` was also keyed by the legacy ``clientes.id``; the
canonical service is keyed by ``customers.id``, the id Customer 360 already
has. ``visits``/``lifetime_amount`` were dropped: no screen read them, and
spend belongs to Sales/BI, not to Fidelidad.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.customers.permissions import CustomerPermissions
from backend.application.loyalty.queries.customer_summary_query import (
    LoyaltyCustomerSummaryQueryService,
)


@dataclass(frozen=True)
class LoyaltyCustomerSummary:
    customer_id: str
    enrolled: bool
    current_points: int
    tier: str | None
    program: str | None = None


class LoyaltyCustomerSummaryQuery:
    def __init__(self, connection, authorization: CustomerAuthorizationPolicy | None = None) -> None:
        self._conn = connection
        self._auth = authorization or CustomerAuthorizationPolicy()

    def get_summary(self, customer_id: str, *, actor_user_id: str) -> LoyaltyCustomerSummary:
        self._auth.require(actor_user_id, CustomerPermissions.LOYALTY_VIEW)
        snapshot = LoyaltyCustomerSummaryQueryService(self._conn).summary_for(customer_id)
        return LoyaltyCustomerSummary(
            customer_id=customer_id, enrolled=snapshot.enrolled,
            current_points=snapshot.available_points, tier=snapshot.tier_name,
            program=snapshot.program_name)
