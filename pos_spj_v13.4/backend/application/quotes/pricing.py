"""QuotePricing — de dónde salen producto y precio de una partida.

Compone lo que ya existe, sin copiar reglas:

* qué se puede ofrecer en la sucursal: ``OrderCaptureCatalogQueryService``
  (activo, vendible, habilitado en la sucursal; misma regla que Pedidos);
* precio de lista y mínimo: ``PricingReadFacade.sale_price`` — el mismo motor
  que el mostrador, con sucursal, cliente, cantidad y canal ``SALES_REP``
  (la cotización la hace un vendedor; una lista de canal SALES_REP aplica aquí
  y también al pedido convertido, que se crea con ese mismo canal).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.domain.quotes.exceptions import QuoteValidationError

QUOTE_CHANNEL = "SALES_REP"


@dataclass(frozen=True, slots=True)
class QuotedProduct:
    product_id: str
    code: str
    name: str
    unit_code: str
    weighed: bool
    list_price: Decimal
    min_price: Decimal | None


class QuotePricing:
    def __init__(self, connection) -> None:
        from backend.application.orders_delivery.queries.order_capture_catalog_query_service import (
            OrderCaptureCatalogQueryService,
        )
        from backend.application.pricing.queries.pricing_read_facade import PricingReadFacade

        self._catalog = OrderCaptureCatalogQueryService(connection)
        self._pricing = PricingReadFacade(connection)

    def search(self, *, branch_id: str, text: str, limit: int):
        return self._catalog.search(branch_id=branch_id, query=text, limit=limit)

    def explain_empty(self, *, branch_id: str, text: str) -> str | None:
        return self._catalog.explain_empty(branch_id=branch_id, query=text)

    def product(self, *, branch_id: str, customer_id: str, product_id: str,
                quantity) -> QuotedProduct:
        item = self._catalog.get(branch_id=branch_id, product_id=product_id)
        if item is None:
            raise QuoteValidationError(
                "Ese producto no se vende en esta sucursal (no está activo, no es vendible "
                "o no está habilitado aquí).")
        resolved = self._pricing.sale_price(
            product_id, branch_id=branch_id, customer_id=customer_id, channel=QUOTE_CHANNEL,
            quantity=Decimal(str(quantity)))
        if resolved.price is None:
            raise QuoteValidationError(
                f"«{item.name}» no tiene precio vigente en Precios; no se puede cotizar.")
        return QuotedProduct(product_id=item.product_id, code=item.code, name=item.name,
                             unit_code=item.unit_code, weighed=item.weighed,
                             list_price=resolved.price, min_price=resolved.min_price)
