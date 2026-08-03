from backend.domain.losses.events import LossEvents, build_loss_event
from backend.shared.ids import is_uuidv7, new_uuid


def test_loss_event_has_distinct_uuidv7_identities():
    entity_id, operation_id = new_uuid(), new_uuid()
    event = build_loss_event(
        LossEvents.LOSS_CASE_SUBMITTED,
        operation_id=operation_id, entity_id=entity_id,
        branch_id=new_uuid(), user_id=new_uuid(),
    )
    assert is_uuidv7(event["event_id"])
    assert event["event_id"] not in {entity_id, operation_id}
    assert entity_id != operation_id


def test_loss_event_serializes_decimal_as_string():
    from decimal import Decimal

    event = build_loss_event(
        LossEvents.LOSS_CASE_CREATED,
        operation_id=new_uuid(), entity_id=new_uuid(), branch_id=new_uuid(),
        user_id=new_uuid(), gross_value=Decimal("12.340"),
    )
    assert event["gross_value"] == "12.340"
