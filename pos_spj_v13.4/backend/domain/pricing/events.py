"""Canonical pricing / costing events (PRC-2).

Published post-commit with distinct event_id / operation_id / entity_id. Replace
the legacy ad-hoc price signals (PRECIO_ACTUALIZADO, historial_precios triggers).
"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.shared.ids import new_uuid


class PricingEvents:
    PRICE_LIST_CREATED = "PRICE_LIST_CREATED"
    PRICE_LIST_APPROVED = "PRICE_LIST_APPROVED"
    PRICE_LIST_ACTIVATED = "PRICE_LIST_ACTIVATED"
    PRODUCT_PRICE_CHANGED = "PRODUCT_PRICE_CHANGED"
    VOLUME_PRICE_CHANGED = "VOLUME_PRICE_CHANGED"
    PRODUCT_COST_UPDATED = "PRODUCT_COST_UPDATED"
    PRICE_BELOW_MINIMUM_AUTHORIZED = "PRICE_BELOW_MINIMUM_AUTHORIZED"


ALL_PRICING_EVENTS = frozenset(
    v for k, v in vars(PricingEvents).items()
    if not k.startswith("_") and isinstance(v, str)
)


def build_pricing_event_payload(
    event_name: str, *, operation_id: str, entity_id: str,
    product_id: str | None = None, branch_id: str | None = None,
    user_id: str | None = None, **extra,
) -> dict:
    if event_name not in ALL_PRICING_EVENTS:
        raise ValueError(f"Evento de pricing desconocido: {event_name}")
    payload = {
        "event_id": new_uuid(), "event_name": event_name,
        "operation_id": operation_id, "entity_id": entity_id,
        "product_id": product_id, "branch_id": branch_id, "user_id": user_id,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_module": "pricing",
    }
    payload.update(extra)
    return payload
