"""LoyaltyCustomerSummaryQuery (§49, exact name from master prompt §57):
"CRM muestra programa/nivel/puntos/tarjeta/recompensas resumidas... acciones
detalladas navegan a Fidelidad."

Reads Fidelidad's own ``loyalty_snapshots`` table directly — read-only,
parameterized, same sanctioned exception as this phase's other summary
queries. ``loyalty_snapshots`` is deliberately the ONLY table read here: it
is the precomputed per-customer summary row Fidelidad itself maintains,
exactly the shape a *summary* query should read rather than re-deriving
totals from the raw ledger or card/tier tables Fidelidad owns —
``tests/architecture/test_customers_crm_does_not_own_loyalty.py`` forbids
every one of those by name; this file must never reference any of them.

**Known, documented gap**: ``loyalty_snapshots.cliente_id`` is the legacy
``clientes.id``, never this bounded context's UUIDv7 ``customers.id`` —
same deferred-to-CRM-21/22 story as the rest of this phase's summaries.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.customers.permissions import CustomerPermissions


@dataclass(frozen=True)
class LoyaltyCustomerSummary:
    customer_id: str
    enrolled: bool
    current_points: int
    tier: str | None
    visits: int
    lifetime_amount: str


class LoyaltyCustomerSummaryQuery:
    def __init__(self, connection, authorization: CustomerAuthorizationPolicy | None = None) -> None:
        self._conn = connection
        self._auth = authorization or CustomerAuthorizationPolicy()

    def get_summary(self, customer_id: str, *, actor_user_id: str) -> LoyaltyCustomerSummary:
        self._auth.require(actor_user_id, CustomerPermissions.LOYALTY_VIEW)
        row = None
        if self._table_exists("loyalty_snapshots"):
            row = self._conn.execute(
                "SELECT puntos_actuales, nivel, visitas, importe_total"
                " FROM loyalty_snapshots WHERE cliente_id=?", (customer_id,)).fetchone()
        if row is None:
            return LoyaltyCustomerSummary(
                customer_id=customer_id, enrolled=False, current_points=0, tier=None,
                visits=0, lifetime_amount="0")
        puntos, nivel, visitas, importe = row
        return LoyaltyCustomerSummary(
            customer_id=customer_id, enrolled=True, current_points=puntos or 0,
            tier=nivel, visits=visitas or 0, lifetime_amount=str(importe or 0))

    def _table_exists(self, name: str) -> bool:
        """Fidelidad is a sibling module, not this bounded context's own
        schema (see module docstring) — same "missing table means nothing
        to contribute" discipline as CustomerHistoryQueryService."""
        return self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone() is not None
