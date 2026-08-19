"""SalesPricingClient — Sales' integration point onto the real Pricing
bounded context (master prompt §6/§14: effective price is composed, never
computed by Sales itself). Mirrors `sales_inventory_client.py`/
`sales_customer_client.py`'s shape: thin, delegates entirely to the real
owning context's own facade.

`backend/application/pricing/queries/pricing_read_facade.py::PricingReadFacade`
is already the documented single canonical read entry point ("for the 44
consumers", its own docstring) — branch-specific, customer-tier-aware, and
volume-tier-aware (confirmed by reading `ProductPriceQueryService.get_sale_price`
before wiring this). It is already Decimal-first, so no float boundary
conversion is needed here (unlike `SalesInventoryClient`/`SalesLoyaltyClient`,
which wrap float-typed legacy services).

Deliberately NOT wired into `SalesCatalogQueryService.search()` (SALES-7) —
that method does one bulk SQL query for a whole grid of products and stays
on the flat BASE-list price for browsing/display speed; resolving each row
through `PricingReadFacade` would mean one query per product (N+1). This
client is for resolving the REAL price of ONE specific product for a
specific customer/quantity at the moment it actually matters — before
`AddSaleLineUseCase` is called with the resolved `unit_price` — not for
populating the whole catalog grid.

Promotions are NOT part of this evaluation — confirmed by research that
`PriceListKind.PROMOTIONAL` exists as an enum value but is never queried by
`ProductPriceQueryService`; time-bound promotional pricing does not exist in
this repository yet (see `backend/application/sales/queries/
benefit_evaluation_service.py` for where that gap is surfaced explicitly,
not hidden).
"""

from __future__ import annotations

from decimal import Decimal

from backend.application.pricing.queries.pricing_read_facade import PricingReadFacade


class SalesPricingClient:
    def __init__(self, connection) -> None:
        self._facade = PricingReadFacade(connection)

    def effective_price(
        self, product_id: str, *, branch_id: str | None = None,
        customer_id: str | None = None, quantity: Decimal | int = 1,
    ) -> Decimal | None:
        """None means the product has no price configured yet — the caller
        decides how to handle that (never silently default to 0)."""
        return self._facade.sale_price_amount(
            product_id, branch_id=branch_id, customer_id=customer_id, quantity=quantity)
