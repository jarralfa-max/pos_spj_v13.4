"""Branch / assortment policy (§13, §29, §33) — who may be offered where.

A product may exist and not be enabled for sale (§29). Consumer channels (POS,
e-commerce, WhatsApp, delivery) never expose internal / non-sellable products
(§13, §33); enabling one for such a channel is rejected. Non-consumer channels
(plant, central warehouse, wholesale) may reference internal products.
"""

from __future__ import annotations

from backend.domain.products.channel_enums import CONSUMER_CHANNELS, SalesChannel
from backend.domain.products.entities.product import Product
from backend.domain.products.exceptions import ChannelNotAllowedError


def ensure_channel_allowed(product: Product, channel: SalesChannel) -> None:
    """A consumer channel may only offer active, sellable, non-internal products."""
    if channel not in CONSUMER_CHANNELS:
        return
    if product.is_internal or not product.sellable:
        raise ChannelNotAllowedError(
            f"El producto no puede ofrecerse en el canal {channel.value}: "
            "es interno o no vendible (§13, §33)")


def can_offer(product: Product, channel: SalesChannel) -> bool:
    try:
        ensure_channel_allowed(product, channel)
        return True
    except ChannelNotAllowedError:
        return False
