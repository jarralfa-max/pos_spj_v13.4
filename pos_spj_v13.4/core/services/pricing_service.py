# core/services/pricing_service.py — SPJ ERP (PRC-8)
"""Legacy price façade → delegates to the canonical Pricing/Costing context.

Historically this service read ``productos.precio`` / ``precios_lista`` /
``precios_volumen`` / ``clientes_lista_precio`` with int ids and float prices
(violating REGLA CERO). It is now a thin shim over the canonical
``ProductPriceQueryService`` (UUIDv7 + Money/Decimal, resolution priority
volumen > lista cliente > lista > base): no legacy price tables, no float pricing.

Only ``get_precio`` had live consumers (``sales_service``); the old list/volume
management methods were dead and were removed. The legacy price tables are dropped
by ``migrations/deferred/legacy_pricing_drop.py``.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from core.db.connection import get_connection

logger = logging.getLogger("spj.pricing")


class PricingService:
    def __init__(self, conn=None):
        self.conn = conn or get_connection()

    def get_precio(self, producto_id: str, cantidad: float = 1.0,
                   lista_id=None, cliente_id: str | None = None,
                   sucursal_id: str | None = None) -> dict:
        """Best applicable price for a product, resolved by the canonical context.

        Returns the legacy dict contract (``precio`` / ``precio_base`` / ``fuente`` /
        ``lista_id`` / ``descuento_pct``) that ``sales_service`` consumes, but reads
        from ``product_price`` / ``volume_price`` (never ``productos.precio``).
        ``fuente == 'base'`` means "no override" for the caller.
        """
        from backend.application.pricing.queries.product_price_query_service import (
            ProductPriceQueryService,
        )

        try:
            qty = Decimal(str(cantidad or 1))
        except Exception:
            qty = Decimal("1")

        resolution = ProductPriceQueryService(self.conn).get_sale_price(
            str(producto_id),
            branch_id=(str(sucursal_id) if sucursal_id else None),
            customer_id=(str(cliente_id) if cliente_id else None),
            quantity=qty)

        precio = float(resolution.price.amount) if resolution.price is not None else 0.0
        source = resolution.source.value  # VOLUME | CUSTOMER_LIST | LIST | BASE | NONE
        fuente = "base" if source in ("BASE", "NONE") else source.lower()
        return {
            "producto_id": str(producto_id),
            "precio": round(precio, 4),
            "precio_base": precio,
            "lista_id": lista_id,
            "fuente": fuente,
            "descuento_pct": 0,
        }
