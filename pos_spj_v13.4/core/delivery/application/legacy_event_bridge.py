from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from core.delivery.domain.events import DeliveryEvents

logger = logging.getLogger("spj.delivery.application.legacy_event_bridge")

LegacyPublisher = Callable[[str, dict[str, Any]], None]


@dataclass(frozen=True, slots=True)
class LegacyDeliveryEvent:
    event_type: str
    payload: dict[str, Any]


LEGACY_DELIVERY_EVENT_DEPRECATION: dict[str, str] = {
    "pedido_delivery_creado": "Bridge temporal desde DELIVERY_ORDER_CREATED; eliminar cuando UI/handlers consuman canónico.",
    "pedido_whatsapp_recibido": "Bridge temporal desde DELIVERY_ORDER_CREATED para consumidores WhatsApp legacy.",
    "pedido_en_ruta": "Bridge temporal desde DELIVERY_OUT_FOR_DELIVERY.",
    "pedido_entregado": "Bridge temporal desde DELIVERY_ORDER_DELIVERED.",
    "stock_liberar_solicitado": "Bridge temporal desde INVENTORY_RELEASE_REQUIRED.",
    "notificacion_whatsapp_enviada": "No se emite desde CUSTOMER_NOTIFICATION_REQUESTED; conservar solo cuando el notifier confirme envío directo legacy.",
}


class LegacyDeliveryEventBridge:
    """Translates canonical delivery events to legacy EventBus names.

    This bridge is intentionally one-way and temporary. Application use cases
    should publish canonical events; old subscribers can keep listening to the
    Spanish legacy names until they migrate.
    """

    CANONICAL_EVENTS: tuple[str, ...] = (
        DeliveryEvents.ORDER_CREATED.value,
        DeliveryEvents.OUT_FOR_DELIVERY.value,
        DeliveryEvents.ORDER_DELIVERED.value,
        DeliveryEvents.INVENTORY_RELEASE_REQUIRED.value,
    )

    def __init__(self, publisher: LegacyPublisher) -> None:
        self.publisher = publisher

    def handle(self, event_type: str, payload: dict[str, Any] | None) -> list[LegacyDeliveryEvent]:
        translated = self.translate(event_type, payload or {})
        for legacy in translated:
            self.publisher(legacy.event_type, legacy.payload)
        return translated

    def translate(self, event_type: str, payload: dict[str, Any]) -> list[LegacyDeliveryEvent]:
        clean = self._without_db(payload)
        order_id = clean.get("order_id")
        if not order_id:
            return []

        if event_type == DeliveryEvents.ORDER_CREATED.value:
            return [
                LegacyDeliveryEvent("pedido_delivery_creado", {"order_id": order_id}),
                LegacyDeliveryEvent(
                    "pedido_whatsapp_recibido",
                    {"order_id": order_id, "canal": clean.get("canal") or clean.get("source_channel") or "whatsapp"},
                ),
            ]
        if event_type == DeliveryEvents.OUT_FOR_DELIVERY.value:
            return [LegacyDeliveryEvent("pedido_en_ruta", {"order_id": order_id})]
        if event_type == DeliveryEvents.ORDER_DELIVERED.value:
            return [
                LegacyDeliveryEvent(
                    "pedido_entregado",
                    {"order_id": order_id, "responsable": clean.get("responsable") or clean.get("usuario") or ""},
                )
            ]
        if event_type == DeliveryEvents.INVENTORY_RELEASE_REQUIRED.value:
            return [LegacyDeliveryEvent("stock_liberar_solicitado", {"order_id": order_id})]
        return []

    @staticmethod
    def _without_db(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: LegacyDeliveryEventBridge._without_db(val) for key, val in value.items() if key != "db"}
        if isinstance(value, list):
            return [LegacyDeliveryEventBridge._without_db(item) for item in value]
        if isinstance(value, tuple):
            return [LegacyDeliveryEventBridge._without_db(item) for item in value]
        return value


def register_legacy_delivery_event_bridge(bus) -> LegacyDeliveryEventBridge:
    """Subscribe bridge handlers to canonical delivery events on an EventBus."""
    bridge = LegacyDeliveryEventBridge(lambda event, payload: bus.publish(event, payload))
    for event_type in LegacyDeliveryEventBridge.CANONICAL_EVENTS:
        bus.subscribe(
            event_type,
            lambda payload, _event_type=event_type: bridge.handle(_event_type, payload),
            priority=-100,
            label=f"legacy_delivery_bridge:{event_type}",
        )
    return bridge
