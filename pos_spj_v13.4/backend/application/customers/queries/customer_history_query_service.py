"""CustomerHistoryQueryService (§29, §57) — the canonical
CustomerActivityTimeline: one chronological feed of everything that
happened to a customer, merged from every bounded context's own audit
log. Reads only; never mutates.

This is the one place in the CRM-0..12 pipeline that deliberately reads
raw SQL from OTHER bounded contexts' tables — a documented exception to
the "never reach into another bounded context's tables" rule CRM-8/9/11
held for *writes*. Reading for display aggregation is a different concern
than writing: nothing here would leave those tables in a state their own
use cases didn't already put them in, and precedent already exists
(``CustomerAccountsReceivableSummaryQuery`` has read Finanzas' own
``cuentas_por_cobrar`` table read-only since CRM-8). Building a
Customer 360/timeline view is *specifically what this pattern is for*.

Correlation to customer_id per source:
  - customers: ``customer_audit_log.customer_id`` — direct.
  - crm: ``crm_audit_log`` has no customer_id column (it's keyed by lead/
    opportunity/activity/task/note id) — correlated via
    ``opportunities.customer_id`` only. Leads are deliberately NOT
    included: a Lead has no customer_id until it converts, and the
    resulting Opportunity's own trail carries the relationship forward
    from there.
  - customer_service: ``customer_service_audit_log`` has no customer_id
    column either — correlated via ``service_cases.customer_id``.
  - customer_credit / customer_privacy: their own audit tables already
    carry ``customer_id`` directly.

Gated by ``AUDIT_VIEW`` (§76) — viewing a customer's full cross-context
history is an audit concern, not a profile-viewing concern.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.customers.permissions import CustomerPermissions
from backend.domain.customers.exceptions import CustomerDomainError


@dataclass(frozen=True)
class CustomerTimelineEntry:
    occurred_at: str
    source_module: str
    action: str
    actor_user_id: str | None
    reason: str
    source_entity_id: str | None


class CustomerHistoryQueryService:
    def __init__(self, connection,
                authorization: CustomerAuthorizationPolicy | None = None) -> None:
        self._conn = connection
        self._auth = authorization or CustomerAuthorizationPolicy()

    def get_timeline(self, customer_id: str, *, actor_user_id: str,
                     limit: int = 200) -> list[CustomerTimelineEntry]:
        self._auth.require(actor_user_id, CustomerPermissions.AUDIT_VIEW)
        entries: list[CustomerTimelineEntry] = []
        entries.extend(self._customers_entries(customer_id))
        entries.extend(self._crm_entries(customer_id))
        entries.extend(self._service_entries(customer_id))
        entries.extend(self._credit_entries(customer_id))
        entries.extend(self._privacy_entries(customer_id))
        entries.sort(key=lambda e: e.occurred_at, reverse=True)
        return entries[:limit]

    def _customers_entries(self, customer_id: str) -> list[CustomerTimelineEntry]:
        if not self._table_exists("customer_audit_log"):
            return []
        rows = self._conn.execute(
            "SELECT action, actor_user_id, reason, created_at FROM customer_audit_log"
            " WHERE customer_id=?", (customer_id,)).fetchall()
        return [CustomerTimelineEntry(
            occurred_at=r[3], source_module="customers", action=r[0], actor_user_id=r[1],
            reason=r[2] or "", source_entity_id=customer_id) for r in rows]

    def _crm_entries(self, customer_id: str) -> list[CustomerTimelineEntry]:
        if not (self._table_exists("crm_audit_log") and self._table_exists("opportunities")):
            return []
        rows = self._conn.execute(
            "SELECT a.action, a.actor_user_id, a.reason, a.created_at, a.opportunity_id"
            " FROM crm_audit_log a"
            " WHERE a.opportunity_id IN (SELECT id FROM opportunities WHERE customer_id=?)",
            (customer_id,)).fetchall()
        return [CustomerTimelineEntry(
            occurred_at=r[3], source_module="crm", action=r[0], actor_user_id=r[1],
            reason=r[2] or "", source_entity_id=r[4]) for r in rows]

    def _service_entries(self, customer_id: str) -> list[CustomerTimelineEntry]:
        if not (self._table_exists("customer_service_audit_log")
                and self._table_exists("service_cases")):
            return []
        rows = self._conn.execute(
            "SELECT a.action, a.actor_user_id, a.reason, a.created_at, a.case_id"
            " FROM customer_service_audit_log a"
            " WHERE a.case_id IN (SELECT id FROM service_cases WHERE customer_id=?)",
            (customer_id,)).fetchall()
        return [CustomerTimelineEntry(
            occurred_at=r[3], source_module="customer_service", action=r[0], actor_user_id=r[1],
            reason=r[2] or "", source_entity_id=r[4]) for r in rows]

    def _credit_entries(self, customer_id: str) -> list[CustomerTimelineEntry]:
        if not self._table_exists("customer_credit_audit_log"):
            return []
        rows = self._conn.execute(
            "SELECT action, actor_user_id, reason, created_at, profile_id"
            " FROM customer_credit_audit_log WHERE customer_id=?", (customer_id,)).fetchall()
        return [CustomerTimelineEntry(
            occurred_at=r[3], source_module="customer_credit", action=r[0], actor_user_id=r[1],
            reason=r[2] or "", source_entity_id=r[4]) for r in rows]

    def _privacy_entries(self, customer_id: str) -> list[CustomerTimelineEntry]:
        if not self._table_exists("customer_privacy_audit_log"):
            return []
        rows = self._conn.execute(
            "SELECT action, actor_user_id, reason, created_at, request_id"
            " FROM customer_privacy_audit_log WHERE customer_id=?", (customer_id,)).fetchall()
        return [CustomerTimelineEntry(
            occurred_at=r[3], source_module="customer_privacy", action=r[0], actor_user_id=r[1],
            reason=r[2] or "", source_entity_id=r[4]) for r in rows]

    def _table_exists(self, name: str) -> bool:
        """Sibling bounded contexts are optional at the schema level (a
        deployment could run migrations up to a point before CRM-8/9/10
        landed, or a test fixture may only load one schema) — a missing
        table means "nothing to contribute", not an error."""
        return self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone() is not None
