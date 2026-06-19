from __future__ import annotations

from typing import Any

from core.delivery.domain.events import DeliveryEvents

from .ports import EventPublisher, GeocodingPort, NoopPublisher, StatusNotifier


class CreateDeliveryOrderUseCase:
    def __init__(
        self,
        *,
        db,
        repository,
        geocoding_service: GeocodingPort | None = None,
        whatsapp_service: StatusNotifier | None = None,
        publisher: EventPublisher = NoopPublisher,
        outbox_repository=None,
    ) -> None:
        self.db = db
        self.repository = repository
        self.geocoding_service = geocoding_service
        self.whatsapp_service = whatsapp_service
        self.publisher = publisher
        self.outbox_repository = outbox_repository

    def execute(self, data: dict[str, Any], usuario: str = "sistema") -> int:
        payload = dict(data or {})
        direccion = (payload.get("direccion") or "").strip()
        if not direccion:
            raise ValueError("No se puede crear pedido sin dirección válida")

        coords = payload.get("coords")
        if coords is None and self.geocoding_service is not None:
            coords = self.geocoding_service.geocode(direccion)
        if coords:
            payload["lat"] = coords.get("lat")
            payload["lng"] = coords.get("lng")
        else:
            payload["lat"] = payload.get("lat")
            payload["lng"] = payload.get("lng")

        payload["usuario"] = usuario
        order_id = self.repository.create_order(payload, commit=False)
        events_to_publish: list[tuple[str, dict[str, Any]]] = []

        operation_id = f"delivery:{order_id}"
        items = payload.get("items") or []
        if items:
            reserved_payload = {
                "order_id": order_id,
                "operation_id": operation_id,
                "items": items,
                "branch_id": payload.get("sucursal_id", 1),
            }
            self._enqueue(DeliveryEvents.ORDER_RESERVED.value, order_id, reserved_payload, operation_id=operation_id)
            events_to_publish.append(("DELIVERY_ORDER_RESERVED", reserved_payload))

        order = self.repository.get_order(order_id) or {}
        notification_payload = {
            "order_id": order_id,
            "canal": "whatsapp",
            "template": "pedido_recibido",
            "params": {"folio": order.get("folio") or payload.get("folio") or f"DEL-{order_id}"},
            "cliente_tel": order.get("cliente_tel", ""),
        }
        self._enqueue(
            DeliveryEvents.CUSTOMER_NOTIFICATION_REQUESTED.value,
            order_id,
            notification_payload,
            operation_id=f"delivery:{order_id}:notify:pedido_recibido",
        )
        created_payload = {
            "_event_type": "DELIVERY_ORDER_CREATED",
            "order_id": order_id,
            "folio": order.get("folio") or payload.get("folio") or f"DEL-{order_id}",
            "direccion": payload.get("direccion"),
            "total": payload.get("total", 0),
            "sucursal_id": payload.get("sucursal_id", 1),
            "usuario": usuario,
        }
        events_to_publish.append(("DELIVERY_ORDER_CREATED", created_payload))
        self.db.commit()

        for event_name, event_payload in events_to_publish:
            self.publisher(event_name, event_payload)
        self._safe_wa_notify(order, "pedido_recibido")
        return order_id

    def _enqueue(self, event_type: str, order_id: int, payload: dict[str, Any], operation_id: str | None = None) -> None:
        if self.outbox_repository is None:
            return
        self.outbox_repository.enqueue(
            event_type=event_type,
            aggregate_id=order_id,
            payload=payload,
            operation_id=operation_id,
            commit=False,
        )

    def _safe_wa_notify(self, order: dict[str, Any], status: str) -> None:
        if self.outbox_repository is not None or self.whatsapp_service is None:
            return
        ok = self.whatsapp_service.notify_status(
            phone=order.get("cliente_tel", ""),
            folio=order.get("folio") or str(order.get("id") or ""),
            status=status,
        )
        self.publisher(
            "notificacion_whatsapp_enviada",
            {"order_id": order.get("id"), "status": status, "ok": bool(ok)},
        )
