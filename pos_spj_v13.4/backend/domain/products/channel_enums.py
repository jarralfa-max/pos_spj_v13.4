"""Sales-channel enums for the products bounded context (§29).

PROD-14. A product exists once (one ``products`` row) and is *enabled* per branch
and per channel — never duplicated by branch, and never carrying an operational
price here (price lives in Pricing). Sales channels distinguish where the product
is offered.
"""

from __future__ import annotations

from enum import Enum


class SalesChannel(str, Enum):
    GLOBAL = "GLOBAL"                 # catálogo global (todas las sucursales/canales)
    POS = "POS"
    ECOMMERCE = "ECOMMERCE"
    WHATSAPP = "WHATSAPP"
    DELIVERY = "DELIVERY"
    WHOLESALE = "WHOLESALE"          # mayoreo
    PLANT = "PLANT"                  # planta
    CENTRAL_WAREHOUSE = "CENTRAL_WAREHOUSE"


# Canales de venta al consumidor: no exponen productos internos ni de proceso (§33).
CONSUMER_CHANNELS = frozenset({
    SalesChannel.POS,
    SalesChannel.ECOMMERCE,
    SalesChannel.WHATSAPP,
    SalesChannel.DELIVERY,
})
