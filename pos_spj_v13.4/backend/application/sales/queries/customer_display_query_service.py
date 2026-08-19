"""CustomerDisplayQueryService — POS-12/§50's read projection for a
customer-facing second screen.

Sales only publishes state for this device, never controls it (§6/§50); no
real customer-display consumer/hardware exists anywhere in this repository
(confirmed by research — zero references). Building a push mechanism to a
device that doesn't exist would be exactly the decorative infrastructure
this pipeline has repeatedly refused to build (outbox dispatcher, Promotions
engine). What genuinely belongs here: a single, honest projection of "what
should this screen show right now", composed from `Sale`'s own already-real
state (mirrors `SaleQueryService.get`'s shape) plus a resolved screen mode.
A future consumer polls this or subscribes to `sales_outbox`'s existing
event stream (`SaleEvents.LINE_ADDED` etc. are already enqueued by every
cart mutation — no new plumbing needed for that half).
"""

from __future__ import annotations

from backend.application.sales.authorization import SalesAuthorizationPolicy
from backend.application.sales.dto import CustomerDisplayLineDTO, CustomerDisplayStateDTO
from backend.application.sales.permissions import SalesPermissions
from backend.domain.sales.enums import SaleStatus
from backend.domain.sales.exceptions import SaleNotFoundError
from backend.infrastructure.db.repositories.sales.sale_repository import SaleRepository

_SCREEN_BY_STATUS = {
    SaleStatus.DRAFT: "CART",
    SaleStatus.ACTIVE: "CART",
    SaleStatus.SUSPENDED: "IDLE",
    SaleStatus.CHECKOUT_PENDING: "PAYMENT_PENDING",
    SaleStatus.PAYMENT_PENDING: "PAYMENT_PENDING",
    SaleStatus.COMPLETED: "THANK_YOU",
    SaleStatus.CANCELLED: "IDLE",
    SaleStatus.RETURNED_PARTIALLY: "IDLE",
    SaleStatus.RETURNED_FULLY: "IDLE",
    SaleStatus.REVERSED: "IDLE",
}


class CustomerDisplayQueryService:
    def __init__(self, connection, authorization: SalesAuthorizationPolicy | None = None) -> None:
        self._connection = connection
        self._auth = authorization or SalesAuthorizationPolicy()

    def current_state(self, sale_id: str, *, requester_user_id: str) -> CustomerDisplayStateDTO:
        self._auth.require(requester_user_id, SalesPermissions.VIEW)
        sale = SaleRepository(self._connection).get(sale_id)
        if sale is None:
            raise SaleNotFoundError(f"Venta {sale_id} no existe")

        customer_name = self._resolve_customer_name(sale.customer_id)
        screen = _SCREEN_BY_STATUS.get(sale.status, "IDLE")
        message = "¡Gracias por su compra!" if screen == "THANK_YOU" else ""
        lines = tuple(
            CustomerDisplayLineDTO(
                name=str(line.product_snapshot.get("name") or line.product_snapshot.get("nombre")
                          or line.product_id),
                quantity=line.quantity.value, unit_price=line.unit_price, line_total=line.line_total,
            )
            for line in sale.lines
        )
        return CustomerDisplayStateDTO(
            sale_id=sale.id, screen=screen, customer_name=customer_name, lines=lines,
            subtotal=sale.totals.gross_subtotal, discount_total=sale.totals.discount_total,
            total=sale.totals.total, message=message,
        )

    def _resolve_customer_name(self, customer_id: str | None) -> str | None:
        if customer_id is None:
            return None
        try:
            row = self._connection.execute(
                "SELECT display_name FROM customers WHERE id=?", (customer_id,)).fetchone()
        except Exception:  # noqa: BLE001 - display name is a courtesy, never blocks the projection
            return None
        return None if row is None else (row["display_name"] if hasattr(row, "keys") else row[0])
