from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


def dto_to_view(dto: Any) -> dict:
    """Single canonical mapper: DeliveryOrderViewDTO → presenter view dict.

    Both the Kanban cards and the list rows render from the dict produced here,
    so there is exactly one projection from the canonical DTO to the board UI.
    Pure function (no SQL, no Qt) — kept here so it can be unit-tested headlessly.
    """
    driver_name = dto.driver_name or "Sin asignar"
    fulfillment = dto.fulfillment_type.value  # "pickup" | "delivery"
    total = float(dto.total)
    return {
        "id": dto.order_id,
        "folio": dto.folio,
        "cliente_nombre": dto.customer_name,
        "cliente_tel": dto.customer_tel,
        "estado": dto.status_legacy,          # legacy Spanish status for filters/columns
        "status_label_es": dto.status_label_es,
        "total": total,
        "monto_total": total,
        "workflow_type": dto.workflow_type,
        "delivery_type": fulfillment,
        "tipo_entrega": fulfillment,
        "direccion": dto.direccion,
        "driver_nombre": driver_name,
        "driver_id": dto.driver_id,
        "adjustment_pending": 1 if dto.adjustment_pending else 0,
        "source": dto.source,
        "origen": dto.source,
        "scheduled_at": dto.scheduled_at,
        "fecha": dto.created_at,
        "created_at": dto.created_at,
        "fecha_solicitud": dto.created_at,
    }


def infer_workflow_for_ui(pedido: dict) -> str:
    workflow = str(pedido.get("workflow_type") or "").strip().lower()
    if workflow:
        return workflow
    estado = str(pedido.get("estado") or "").strip().lower()
    delivery_type = str(pedido.get("delivery_type") or pedido.get("tipo_entrega") or "").strip().lower()
    if delivery_type in ("pickup", "sucursal", "mostrador", "counter"):
        return "counter"
    if pedido.get("scheduled_at") or estado in ("programado", "scheduled"):
        return "scheduled"
    return "delivery"


def matches_operational_tab(pedido: dict, tab_key: str | None) -> bool:
    if not tab_key:
        return True
    key = (tab_key or "").strip().lower()
    estado = str(pedido.get("estado") or "").strip().lower()
    workflow = infer_workflow_for_ui(pedido)
    adj_pending = bool(int(pedido.get("adjustment_pending") or 0))
    if key == "counter":
        return workflow == "counter"
    if key == "delivery":
        return workflow == "delivery" and estado != "programado"
    if key == "scheduled":
        return workflow == "scheduled" or estado in ("programado", "scheduled")
    if key == "ajustes":
        return adj_pending
    if key == "historial":
        return estado in ("entregado", "cancelado")
    return True


def matches_scheduled_window(pedido: dict, window_key: str) -> bool:
    key = (window_key or "all").strip().lower()
    if key == "all":
        return True
    scheduled_at = pedido.get("scheduled_at") or pedido.get("fecha_programada")
    if not scheduled_at:
        return False
    try:
        dt = datetime.fromisoformat(str(scheduled_at).replace("Z", "+00:00"))
    except Exception:
        return False
    now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
    d0 = now.date()
    dd = dt.date()
    if key == "today":
        return dd == d0
    if key == "tomorrow":
        return dd == d0 + timedelta(days=1)
    if key == "week":
        return d0 <= dd <= d0 + timedelta(days=7)
    if key == "month":
        return d0 <= dd <= d0 + timedelta(days=30)
    return True

