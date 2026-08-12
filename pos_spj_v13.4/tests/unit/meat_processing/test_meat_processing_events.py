from decimal import Decimal

import pytest

from backend.domain.meat_processing.events import (
    ALL_MEAT_PROCESSING_EVENTS,
    MeatProcessingEvents,
    build_meat_processing_event,
)
from backend.shared.ids import is_uuidv7, new_uuid


def test_event_has_distinct_uuidv7_identities():
    entity_id, operation_id = new_uuid(), new_uuid()
    event = build_meat_processing_event(
        MeatProcessingEvents.PROCESSING_ORDER_CREATED,
        operation_id=operation_id, entity_id=entity_id,
        branch_id=new_uuid(), user_id=new_uuid(),
    )
    assert is_uuidv7(event["event_id"])
    assert event["event_id"] not in {entity_id, operation_id}
    assert entity_id != operation_id
    assert event["source_module"] == "meat_processing"


def test_event_serializes_decimal_as_string():
    event = build_meat_processing_event(
        MeatProcessingEvents.PROCESSING_WEIGHT_CAPTURED,
        operation_id=new_uuid(), entity_id=new_uuid(), branch_id=new_uuid(),
        user_id=new_uuid(), net_weight=Decimal("12.340"),
    )
    assert event["net_weight"] == "12.340"


def test_unknown_event_name_is_rejected():
    with pytest.raises(ValueError):
        build_meat_processing_event(
            "NOT_A_CANONICAL_EVENT",
            operation_id=new_uuid(), entity_id=new_uuid(),
            branch_id=new_uuid(), user_id=new_uuid(),
        )


def test_operation_id_and_entity_id_must_differ():
    same_id = new_uuid()
    with pytest.raises(ValueError):
        build_meat_processing_event(
            MeatProcessingEvents.PROCESSING_ORDER_CREATED,
            operation_id=same_id, entity_id=same_id,
            branch_id=new_uuid(), user_id=new_uuid(),
        )


def test_canonical_catalog_covers_order_lifecycle_and_core_entities():
    expected = {
        MeatProcessingEvents.PRODUCTION_PLAN_CREATED,
        MeatProcessingEvents.PRODUCTION_PLAN_APPROVED,
        MeatProcessingEvents.PRODUCTION_PLAN_CANCELLED,
        MeatProcessingEvents.PRODUCTION_PLAN_LINE_CONVERTED,
        MeatProcessingEvents.PRODUCTION_PLAN_CONVERTED,
        MeatProcessingEvents.PROCESSING_ORDER_CREATED,
        MeatProcessingEvents.PROCESSING_ORDER_APPROVED,
        MeatProcessingEvents.PROCESSING_ORDER_RELEASED,
        MeatProcessingEvents.PROCESSING_ORDER_STARTED,
        MeatProcessingEvents.PROCESSING_ORDER_PAUSED,
        MeatProcessingEvents.PROCESSING_ORDER_RESUMED,
        MeatProcessingEvents.PROCESSING_ORDER_COMPLETED,
        MeatProcessingEvents.PROCESSING_ORDER_CLOSED,
        MeatProcessingEvents.PROCESSING_ORDER_CANCELLED,
        MeatProcessingEvents.PROCESSING_ORDER_REVERSED,
        MeatProcessingEvents.PROCESSING_MATERIAL_CONSUMED,
        MeatProcessingEvents.PROCESSING_WEIGHT_CAPTURED,
        MeatProcessingEvents.PROCESSING_OUTPUT_PRODUCED,
        MeatProcessingEvents.PROCESSING_YIELD_CALCULATED,
        MeatProcessingEvents.PROCESSING_YIELD_OUT_OF_TOLERANCE,
    }
    assert expected.issubset(ALL_MEAT_PROCESSING_EVENTS)
