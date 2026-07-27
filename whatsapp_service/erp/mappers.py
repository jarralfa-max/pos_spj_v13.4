from __future__ import annotations

from typing import Any, Dict


def normalize_whatsapp_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Map heterogeneous WA payload keys into a canonical internal contract in English."""
    return {
        "customer_phone": payload.get("customer_phone") or payload.get("cliente_telefono") or payload.get("cliente_tel") or payload.get("telefono") or "",
        "customer_name": payload.get("customer_name") or payload.get("cliente_nombre") or payload.get("cliente") or "",
        "branch_id": payload.get("branch_id") or payload.get("sucursal_id"),
        "delivery_address": payload.get("delivery_address") or payload.get("direccion_entrega") or payload.get("direccion") or "",
        "workflow_type": payload.get("workflow_type") or "delivery",
        "delivery_type": payload.get("delivery_type") or payload.get("tipo_entrega") or "home_delivery",
        "scheduled_at": payload.get("scheduled_at") or payload.get("fecha_entrega_programada"),
        "items": payload.get("items") or [],
    }
