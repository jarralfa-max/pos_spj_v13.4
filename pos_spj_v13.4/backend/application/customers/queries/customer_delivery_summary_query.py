"""CustomerDeliverySummaryQuery (§49): "Pedidos/Delivery... Delivery
administra zona/tarifa/ruta/repartidor/estado." CRM only reads a summary +
recent incidents; Delivery remains the source of truth for routing/driver
assignment.

Reads Delivery's own ``delivery_orders``/``delivery_order_history`` tables
read-only — same sanctioned exception as ``CustomerAccountsReceivableSummary
Query``/``CustomerOrdersSummaryQuery``.

``delivery_order_history`` has no dedicated "incident" flag — ``reason``
(free text, only populated for exception-path transitions, see
``migrations/093_create_delivery_core.sql``) is the closest thing, so a row
counts as an "incident" here when ``reason`` is non-empty, same
"repurpose the closest existing signal instead of inventing a parallel one"
discipline this bounded context has followed since CRM-6.

**Known, documented gap**: ``delivery_orders.cliente_id`` is declared
``INTEGER`` — a THIRD, mutually incompatible identity space alongside the
legacy ``clientes.id`` (TEXT) and this bounded context's UUIDv7
``customers.id`` (TEXT). Comparing a UUIDv7 string against an INTEGER
column never raises (SQLite's type-affinity rules) and never matches —
this query correctly returns an empty summary for every customer today,
same deferred-to-CRM-21/22 story as the rest of this phase.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.customers.permissions import CustomerPermissions


@dataclass(frozen=True)
class DeliveryIncident:
    order_id: str
    reason: str
    occurred_at: str | None


@dataclass(frozen=True)
class CustomerDeliverySummary:
    customer_id: str
    total_deliveries: int
    open_deliveries: int
    last_delivery_status: str | None
    recent_incidents: tuple[DeliveryIncident, ...]


_OPEN_STATES = ("pendiente", "asignado", "en_ruta", "preparando")


class CustomerDeliverySummaryQuery:
    def __init__(self, connection, authorization: CustomerAuthorizationPolicy | None = None) -> None:
        self._conn = connection
        self._auth = authorization or CustomerAuthorizationPolicy()

    def get_summary(self, customer_id: str, *, actor_user_id: str) -> CustomerDeliverySummary:
        self._auth.require(actor_user_id, CustomerPermissions.DELIVERY_VIEW)
        if not self._table_exists("delivery_orders"):
            return CustomerDeliverySummary(
                customer_id=customer_id, total_deliveries=0, open_deliveries=0,
                last_delivery_status=None, recent_incidents=())

        orders = self._conn.execute(
            "SELECT id, estado FROM delivery_orders WHERE cliente_id=?"
            " ORDER BY fecha DESC", (customer_id,)).fetchall()
        total = len(orders)
        open_count = sum(1 for _id, estado in orders if estado in _OPEN_STATES)
        last_status = orders[0][1] if orders else None

        incidents: tuple[DeliveryIncident, ...] = ()
        if orders:
            order_ids = tuple(order_id for order_id, _estado in orders)
            placeholders = ",".join("?" for _ in order_ids)
            rows = self._conn.execute(
                f"SELECT order_id, reason, fecha FROM delivery_order_history"
                f" WHERE order_id IN ({placeholders}) AND reason IS NOT NULL AND reason != ''"
                " ORDER BY fecha DESC LIMIT 10", order_ids).fetchall()
            incidents = tuple(
                DeliveryIncident(order_id=str(order_id), reason=reason, occurred_at=occurred_at)
                for order_id, reason, occurred_at in rows)

        return CustomerDeliverySummary(
            customer_id=customer_id, total_deliveries=total, open_deliveries=open_count,
            last_delivery_status=last_status, recent_incidents=incidents)

    def _table_exists(self, name: str) -> bool:
        """Delivery is a sibling module, not this bounded context's own
        schema (see module docstring) — same "missing table means nothing
        to contribute" discipline as CustomerHistoryQueryService."""
        return self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone() is not None
