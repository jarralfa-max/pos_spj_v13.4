"""DeliveryFeePolicy (master prompt §22): the delivery fee is always
data-driven from the resolved `DeliveryZone`, never hardcoded and never a
side effect of product pricing (Delivery does not modify product prices,
§22). Pure: the caller resolves the matching zone (a repository lookup) and
hands it to this policy along with the order's subtotal.
"""

from __future__ import annotations

from decimal import Decimal

from backend.domain.orders_delivery.delivery_zone import DeliveryZone
from backend.domain.orders_delivery.exceptions import DeliveryZoneNotAvailableError


class DeliveryFeePolicy:
    @staticmethod
    def resolve_zone(zones: list[DeliveryZone], *, postal_code: str) -> DeliveryZone:
        for zone in zones:
            if zone.active and zone.covers_postal_code(postal_code):
                return zone
        raise DeliveryZoneNotAvailableError(
            f"No hay una zona de entrega activa para el código postal {postal_code}")

    @staticmethod
    def ensure_minimum_order(zone: DeliveryZone, *, order_subtotal: Decimal) -> None:
        if order_subtotal < zone.minimum_order:
            raise DeliveryZoneNotAvailableError(
                f"El pedido mínimo para la zona {zone.name} es {zone.minimum_order}")

    @staticmethod
    def calculate_fee(zone: DeliveryZone, *, order_subtotal: Decimal) -> Decimal:
        DeliveryFeePolicy.ensure_minimum_order(zone, order_subtotal=order_subtotal)
        return zone.fee_for_order_total(order_subtotal)
