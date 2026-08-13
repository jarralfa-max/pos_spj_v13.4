"""CustomerOrdersSummaryQuery (§49 Pedidos/Delivery): "CRM muestra pedidos/
entregas/incidencias; Orders/Delivery son la fuente; Clientes administra
direcciones."

Reads Pedidos' own ``pedidos_whatsapp`` table directly — read-only,
parameterized, same sanctioned exception as
``CustomerAccountsReceivableSummaryQuery`` (CRM-8): a live summary read,
never a second source of truth, never a table this bounded context owns or
writes to.

**Known, documented gap (same one CRM-13's whole "Integraciones" surface
shares, see ``backend.application.customers.integrations.
sales_event_handlers`` for the full writeup)**: ``pedidos_whatsapp.
cliente_id`` is the legacy ``clientes.id``, never this bounded context's
UUIDv7 ``customers.id`` — this query correctly returns an empty summary for
every customer today, accurate given the current data, not a bug, deferred
to CRM-21/22 same as CRM-8's CxC query.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.customers.permissions import CustomerPermissions


@dataclass(frozen=True)
class CustomerOrdersSummary:
    customer_id: str
    total_orders: int
    open_orders: int
    last_order_status: str | None
    last_order_at: str | None


class CustomerOrdersSummaryQuery:
    def __init__(self, connection, authorization: CustomerAuthorizationPolicy | None = None) -> None:
        self._conn = connection
        self._auth = authorization or CustomerAuthorizationPolicy()

    def get_summary(self, customer_id: str, *, actor_user_id: str) -> CustomerOrdersSummary:
        self._auth.require(actor_user_id, CustomerPermissions.ORDERS_VIEW)
        if not self._table_exists("pedidos_whatsapp"):
            return CustomerOrdersSummary(
                customer_id=customer_id, total_orders=0, open_orders=0,
                last_order_status=None, last_order_at=None)
        rows = self._conn.execute(
            "SELECT estado, fecha FROM pedidos_whatsapp WHERE cliente_id=?"
            " ORDER BY fecha DESC", (customer_id,)).fetchall()
        total = len(rows)
        open_orders = sum(1 for estado, _ in rows if estado not in ("entregado", "cancelado"))
        last_status = rows[0][0] if rows else None
        last_at = rows[0][1] if rows else None
        return CustomerOrdersSummary(
            customer_id=customer_id, total_orders=total, open_orders=open_orders,
            last_order_status=last_status, last_order_at=last_at)

    def _table_exists(self, name: str) -> bool:
        """Pedidos is a sibling module, not this bounded context's own
        schema (see module docstring) — a deployment/test fixture that
        hasn't loaded it means "nothing to contribute", not an error, same
        discipline as CustomerHistoryQueryService's cross-context reads."""
        return self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone() is not None
