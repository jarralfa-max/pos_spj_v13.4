"""Precio que se cobra en el POS — una sola regla (auditoría de Ventas V04).

Lo usan los casos de uso del carrito (al agregar, cambiar cantidad o cliente) y
la vista previa que muestra el diálogo de peso: el cajero ve el MISMO precio
que después se cobra. Precios decide (sucursal, cliente, cantidad, canal POS);
si no responde o el producto no tiene precio, devuelve None y manda el del
catálogo. Nunca bloquea la venta por una consulta de precio que falla.
"""

from __future__ import annotations

import logging
from decimal import Decimal

logger = logging.getLogger("spj.sales.pricing")


def resolve_sale_price(pricing, *, branch_id: str, customer_id: str | None,
                       product_id: str, quantity) -> Decimal | None:
    if pricing is None:
        return None
    try:
        return pricing.effective_price(product_id, branch_id=branch_id,
                                       customer_id=customer_id, quantity=quantity)
    except Exception:  # noqa: BLE001 - se cobra el precio del catálogo
        logger.exception("No se pudo resolver el precio de %s; se usa el del catálogo",
                         product_id)
        return None


class SalePricePreviewService:
    def amount(self, *, sale_id, product_id, quantity, requester_user_id):
        price = self.price(sale_id=sale_id, product_id=product_id, quantity=quantity,
                           requester_user_id=requester_user_id)
        return None if price is None else price * quantity

    """Vista previa del precio para una venta en curso (sin efectos)."""

    def __init__(self, connection, pricing, authorization) -> None:
        from backend.infrastructure.db.repositories.sales.sale_repository import SaleRepository
        self._repo = SaleRepository(connection)
        self._pricing = pricing
        self._auth = authorization

    def price(self, *, sale_id: str, product_id: str, quantity,
              requester_user_id: str) -> Decimal | None:
        sale = self._repo.get(sale_id)
        if sale is None or not self._auth.can_access_branch(requester_user_id, sale.branch_id):
            return None
        return resolve_sale_price(self._pricing, branch_id=sale.branch_id,
                                  customer_id=sale.customer_id, product_id=product_id,
                                  quantity=quantity)
