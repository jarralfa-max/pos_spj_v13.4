"""ORD-2 — the canonical Order event catalog/payload contract. This is the
target vocabulary meant to eventually replace the triplicated
core/events/event_bus.py constants + core/delivery/domain/events.py's
DeliveryEvents + backend/shared/events/event_names.py subset (see
docs/refactor/orders_delivery_legacy_inventory.md §2) — not wired into the
live EventBus yet."""

from __future__ import annotations

import pytest

from backend.domain.orders_delivery.events import (
    ALL_ORDER_EVENTS,
    OrderEvents,
    order_event_payload,
)
from backend.shared.ids import new_uuid


def test_all_order_events_are_uppercase_strings():
    assert len(ALL_ORDER_EVENTS) >= 15
    for value in ALL_ORDER_EVENTS:
        assert isinstance(value, str) and value == value.upper()


def test_no_duplicate_event_values():
    values = [v for k, v in vars(OrderEvents).items() if k.isupper()]
    assert len(values) == len(set(values))


def test_payload_rejects_unknown_event():
    with pytest.raises(ValueError):
        order_event_payload(
            "NOT_A_REAL_EVENT", operation_id=new_uuid(), entity_id=new_uuid(),
            branch_id=new_uuid(), user_id=new_uuid())


def test_payload_requires_uuidv7_fields():
    with pytest.raises(ValueError):
        order_event_payload(
            OrderEvents.CREATED, operation_id="not-a-uuid", entity_id=new_uuid(),
            branch_id=new_uuid(), user_id=new_uuid())


def test_payload_shape_and_extra_fields():
    op, entity, branch, user = new_uuid(), new_uuid(), new_uuid(), new_uuid()
    payload = order_event_payload(
        OrderEvents.CONFIRMED, operation_id=op, entity_id=entity,
        branch_id=branch, user_id=user, order_number="PED-2026-000001")
    assert payload["event_name"] == OrderEvents.CONFIRMED
    assert payload["operation_id"] == op
    assert payload["entity_id"] == entity
    assert payload["branch_id"] == branch
    assert payload["user_id"] == user
    assert payload["source_module"] == "orders_delivery"
    assert payload["payload"] == {"order_number": "PED-2026-000001"}
    assert payload["event_id"] not in {op, entity}
