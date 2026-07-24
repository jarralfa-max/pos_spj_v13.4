"""PricingReadFacade — single canonical read entry for the 44 consumers (PRC-6).

POS / Ventas / BI / Tickets / Fidelidad / Compras adopt this facade instead of
reading ``productos.precio`` / ``precio_compra`` / ``precios_lista`` directly. It
composes ``ProductPriceQueryService`` + ``ProductCostQueryService`` and exposes
Decimal-first results (no Money leak into legacy call sites, no float).

Everything is UUID-keyed (REGLA CERO). ``sale_price`` / ``unit_cost`` return the
canonical Decimal or ``None`` when the product has no price/cost yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.application.pricing.queries.product_price_query_service import (
    ProductCostQueryService,
    ProductPriceQueryService,
)


@dataclass(frozen=True)
class ResolvedSalePrice:
    price: Decimal | None
    source: str
    min_price: Decimal | None
    below_minimum: bool
    currency: str


class PricingReadFacade:
    def __init__(self, connection) -> None:
        self._prices = ProductPriceQueryService(connection)
        self._costs = ProductCostQueryService(connection)

    def sale_price(
        self,
        product_id: str,
        *,
        branch_id: str | None = None,
        customer_id: str | None = None,
        channel: str | None = None,
        quantity: Decimal | int | str = 1,
    ) -> ResolvedSalePrice:
        r = self._prices.get_sale_price(
            product_id, branch_id=branch_id, customer_id=customer_id,
            channel=channel, quantity=Decimal(str(quantity)))
        return ResolvedSalePrice(
            price=None if r.price is None else r.price.amount,
            source=r.source.value,
            min_price=None if r.min_price is None else r.min_price.amount,
            below_minimum=r.below_minimum,
            currency=(r.price.currency if r.price else "MXN"))

    def sale_price_amount(self, product_id: str, **kw) -> Decimal | None:
        """Convenience: just the resolved Decimal price (or None)."""
        return self.sale_price(product_id, **kw).price

    def unit_cost(self, product_id: str, branch_id: str | None = None) -> Decimal | None:
        cost = self._costs.get_effective_cost(product_id, branch_id)
        return None if cost is None else cost.amount

    def average_cost(self, product_id: str, branch_id: str | None = None) -> Decimal | None:
        cost = self._costs.get_average_cost(product_id, branch_id)
        return None if cost is None else cost.amount
