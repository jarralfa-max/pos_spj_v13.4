from backend.shared.events import DomainEvent, EventDispatcher, EventName, InMemoryEventBus, create_domain_event


class LegacyRecorder:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict]] = []

    def publish(self, event_name: str, payload: dict) -> None:
        self.published.append((event_name, payload))


def test_domain_event_contract_requires_operation_and_user_context() -> None:
    event = create_domain_event(
        event_name=EventName.SALE_COMPLETED,
        operation_id="op-1",
        entity_id="sale-1",
        branch_id="branch-1",
        user_name="admin",
        source_module="sales",
        payload={"total": "100.00"},
    )

    serialized = event.to_dict()
    restored = DomainEvent.from_dict(serialized)

    assert serialized["event_name"] == "SALE_COMPLETED"
    assert serialized["operation_id"] == "op-1"
    assert serialized["payload"] == {"total": "100.00"}
    assert restored == event


def test_domain_event_rejects_missing_required_context() -> None:
    try:
        create_domain_event(
            event_name=EventName.PRODUCT_CREATED,
            operation_id="",
            entity_id="product-1",
            branch_id="branch-1",
            source_module="products",
            user_name="admin",
        )
    except ValueError as exc:
        assert "operation_id" in str(exc)
    else:
        raise AssertionError("DomainEvent should reject missing operation_id")


def test_in_memory_event_bus_dispatches_typed_events_to_subscribers() -> None:
    bus = InMemoryEventBus()
    received = []
    event = create_domain_event(
        event_name=EventName.WASTE_REGISTERED,
        operation_id="op-2",
        entity_id="waste-1",
        branch_id="branch-1",
        source_module="waste",
        user_id="user-1",
    )

    bus.subscribe(EventName.WASTE_REGISTERED, received.append)
    bus.publish(event)

    assert received == [event]


def test_event_dispatcher_mirrors_typed_events_to_legacy_bus() -> None:
    bus = InMemoryEventBus()
    legacy = LegacyRecorder()
    dispatcher = EventDispatcher(bus, legacy)
    received = []
    event = create_domain_event(
        event_name=EventName.CASH_Z_CUT_GENERATED,
        operation_id="op-3",
        entity_id="z-1",
        branch_id="branch-1",
        source_module="cash_register",
        user_name="cajero",
    )

    bus.subscribe(EventName.CASH_Z_CUT_GENERATED, received.append)
    dispatcher.dispatch(event)

    assert received == [event]
    assert legacy.published == [("CASH_Z_CUT_GENERATED", event.to_dict())]
