from __future__ import annotations
from datetime import datetime, timezone


def build_ai_prompt_context(message_text: str, ctx, *, allowed_intents: list[str]) -> dict:
    preview = (message_text or "")[:500]
    return {
        "message": preview,
        "current_state": str(getattr(getattr(ctx, "state", ""), "value", getattr(ctx, "state", "idle"))),
        "branch": {
            "id": getattr(ctx, "sucursal_id", None),
            "name": getattr(ctx, "sucursal_nombre", ""),
        },
        "cart": [
            {"name": i.nombre, "qty": i.cantidad, "unit": i.unidad}
            for i in getattr(ctx, "pedido_items", [])[:20]
        ],
        "whatsapp_number_type": getattr(ctx, "numero_tipo", ""),
        "allowed_intents": allowed_intents,
        "business_rules": {
            "scheduled_orders_require_date": True,
            "delivery_requires_address": True,
            "weight_adjustment_tolerance_units": 0.2,
            "global_number_requires_branch": True,
        },
        "now_utc": datetime.now(timezone.utc).isoformat(),
        "timezone": "UTC",
    }

