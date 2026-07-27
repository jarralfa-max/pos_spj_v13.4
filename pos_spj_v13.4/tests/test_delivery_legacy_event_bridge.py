from core.delivery.application.legacy_event_bridge import (
    LEGACY_DELIVERY_EVENT_DEPRECATION,
    LegacyDeliveryEventBridge,
    register_legacy_delivery_event_bridge,
)
from core.delivery.domain.events import DeliveryEvents
from core.events.event_bus import EventBus


def test_bridge_translates_canonical_delivery_events_without_db_payload():
    emitted = []
    bridge = LegacyDeliveryEventBridge(lambda event, payload: emitted.append((event, payload)))

    translated = bridge.handle(
        DeliveryEvents.ORDER_DELIVERED.value,
        {"order_id": 7, "responsable": "r1", "db": object()},
    )

    assert [(event.event_type, event.payload) for event in translated] == [
        ("pedido_entregado", {"order_id": 7, "responsable": "r1"})
    ]
    assert emitted == [("pedido_entregado", {"order_id": 7, "responsable": "r1"})]
    assert "db" not in emitted[0][1]


def test_bridge_maps_created_route_and_inventory_release_events():
    emitted = []
    bridge = LegacyDeliveryEventBridge(lambda event, payload: emitted.append((event, payload)))

    bridge.handle(DeliveryEvents.ORDER_CREATED.value, {"order_id": 1, "source_channel": "whatsapp"})
    bridge.handle(DeliveryEvents.OUT_FOR_DELIVERY.value, {"order_id": 1, "driver_id": 9})
    bridge.handle(DeliveryEvents.INVENTORY_RELEASE_REQUIRED.value, {"order_id": 1, "operation_id": "delivery:1"})

    assert emitted == [
        ("pedido_delivery_creado", {"order_id": 1}),
        ("pedido_whatsapp_recibido", {"order_id": 1, "canal": "whatsapp"}),
        ("pedido_en_ruta", {"order_id": 1}),
        ("stock_liberar_solicitado", {"order_id": 1}),
    ]


def test_register_bridge_on_event_bus_publishes_legacy_events():
    bus = EventBus()
    bus.clear_handlers()
    received = []
    for event_name in ("pedido_delivery_creado", "pedido_whatsapp_recibido", "pedido_en_ruta"):
        bus.subscribe(event_name, lambda payload, _event_name=event_name: received.append((_event_name, payload)))

    register_legacy_delivery_event_bridge(bus)
    bus.publish(DeliveryEvents.ORDER_CREATED.value, {"order_id": 5})
    bus.publish(DeliveryEvents.OUT_FOR_DELIVERY.value, {"order_id": 5})

    assert [event for event, _payload in received] == [
        "pedido_delivery_creado",
        "pedido_whatsapp_recibido",
        "pedido_en_ruta",
    ]
    assert all("db" not in payload for _event, payload in received)
    bus.clear_handlers()


def test_legacy_deprecation_catalog_documents_events_to_remove_later():
    assert {
        "pedido_delivery_creado",
        "pedido_whatsapp_recibido",
        "pedido_en_ruta",
        "pedido_entregado",
        "stock_liberar_solicitado",
        "notificacion_whatsapp_enviada",
    } <= set(LEGACY_DELIVERY_EVENT_DEPRECATION)
