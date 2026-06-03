from core.delivery.domain.events import CRITICAL_OUTBOX_EVENTS, DeliveryEvents, required_payload_fields


def test_event_catalog_documents_required_payloads():
    assert required_payload_fields(DeliveryEvents.ORDER_CREATED) == (
        "order_id",
        "folio",
        "direccion",
        "total",
        "sucursal_id",
        "usuario",
    )
    assert required_payload_fields("INVENTORY_COMMIT_REQUIRED") == (
        "order_id",
        "operation_id",
        "items",
        "sucursal_id",
    )


def test_critical_events_are_identified_for_future_outbox():
    assert DeliveryEvents.INVENTORY_COMMIT_REQUIRED in CRITICAL_OUTBOX_EVENTS
    assert DeliveryEvents.CUSTOMER_NOTIFICATION_REQUESTED in CRITICAL_OUTBOX_EVENTS
    assert DeliveryEvents.ORDER_PREPARING not in CRITICAL_OUTBOX_EVENTS
