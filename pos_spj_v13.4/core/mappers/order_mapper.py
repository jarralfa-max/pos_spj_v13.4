from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable

from core.domain.order_models import DeliveryType, OrderItem, OrderStatus, OrderWorkflowType, WhatsAppOrder
from core.mappers.status_mapper import to_domain_status, to_legacy_status


def _infer_workflow(delivery_type_legacy: str, scheduled_at: Any) -> OrderWorkflowType:
    if scheduled_at:
        return OrderWorkflowType.SCHEDULED
    if (delivery_type_legacy or "").strip().lower() == "sucursal":
        return OrderWorkflowType.COUNTER
    return OrderWorkflowType.DELIVERY


def _map_delivery_type(delivery_type_legacy: str) -> DeliveryType:
    return DeliveryType.PICKUP if (delivery_type_legacy or "").strip().lower() == "sucursal" else DeliveryType.HOME_DELIVERY


def legacy_sale_to_whatsapp_order(row: Dict[str, Any], items: Iterable[Dict[str, Any]] = ()) -> WhatsAppOrder:
    scheduled_at = row.get("scheduled_at") or row.get("fecha_entrega_programada")
    parsed_scheduled = None
    if isinstance(scheduled_at, str) and scheduled_at:
        try:
            parsed_scheduled = datetime.fromisoformat(scheduled_at)
        except ValueError:
            parsed_scheduled = None

    mapped_items = [
        OrderItem(
            product_id=item.get("product_id"),
            product_name=item.get("nombre") or item.get("product_name") or "",
            quantity=float(item.get("cantidad") or item.get("quantity") or 0),
            unit_price=float(item.get("precio_unitario") or item.get("unit_price") or 0),
            subtotal=float(item.get("subtotal") or 0),
            unit=item.get("unidad") or item.get("unit") or "kg",
        )
        for item in items
    ]

    legacy_delivery_type = row.get("tipo_entrega") or row.get("delivery_type") or "domicilio"
    workflow = _infer_workflow(legacy_delivery_type, parsed_scheduled)

    return WhatsAppOrder(
        order_id=row.get("delivery_order_id") or row.get("id"),
        sale_id=row.get("venta_id") or row.get("sale_id") or row.get("id"),
        branch_id=row.get("sucursal_id") or row.get("branch_id"),
        customer_id=row.get("cliente_id") or row.get("customer_id"),
        customer_name=row.get("cliente_nombre") or row.get("customer_name") or "",
        customer_phone=row.get("cliente_tel") or row.get("telefono") or row.get("customer_phone") or "",
        delivery_address=row.get("direccion_entrega") or row.get("direccion") or row.get("delivery_address") or "",
        workflow_type=workflow,
        delivery_type=_map_delivery_type(legacy_delivery_type),
        status=to_domain_status(row.get("estado") or row.get("status") or "pendiente"),
        scheduled_at=parsed_scheduled,
        source_channel=row.get("source_channel") or "whatsapp",
        items=mapped_items,
    )


def whatsapp_order_to_legacy_sale(order: WhatsAppOrder) -> Dict[str, Any]:
    return {
        "id": order.sale_id,
        "sucursal_id": order.branch_id,
        "cliente_id": order.customer_id,
        "estado": to_legacy_status(order.status),
        "tipo_entrega": "sucursal" if order.delivery_type == DeliveryType.PICKUP else "domicilio",
        "direccion_entrega": order.delivery_address,
        "scheduled_at": order.scheduled_at.isoformat() if order.scheduled_at else None,
        "workflow_type": order.workflow_type.value,
        "source_channel": order.source_channel,
    }


def whatsapp_payload_to_order(payload: Dict[str, Any]) -> WhatsAppOrder:
    return WhatsAppOrder(
        branch_id=payload.get("branch_id"),
        customer_name=payload.get("customer_name") or "",
        customer_phone=payload.get("customer_phone") or "",
        delivery_address=payload.get("delivery_address") or "",
        workflow_type=OrderWorkflowType(payload.get("workflow_type") or "delivery"),
        delivery_type=DeliveryType(payload.get("delivery_type") or "home_delivery"),
        status=OrderStatus(payload.get("status") or "pending"),
    )
