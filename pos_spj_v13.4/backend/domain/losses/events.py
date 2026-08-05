"""Canonical Losses event names and JSON-safe event envelope builder."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from backend.shared.ids import new_uuid, validate_uuidv7


class LossEvents:
    LOSS_CASE_CREATED = "LOSS_CASE_CREATED"
    LOSS_CASE_SUBMITTED = "LOSS_CASE_SUBMITTED"
    LOSS_CASE_REVIEW_STARTED = "LOSS_CASE_REVIEW_STARTED"
    LOSS_CASE_APPROVED = "LOSS_CASE_APPROVED"
    LOSS_CASE_REJECTED = "LOSS_CASE_REJECTED"
    LOSS_INVENTORY_POSTING_REQUESTED = "LOSS_INVENTORY_POSTING_REQUESTED"
    LOSS_INVENTORY_POSTED = "LOSS_INVENTORY_POSTED"
    LOSS_INVENTORY_REVERSED = "LOSS_INVENTORY_REVERSED"
    LOSS_CASE_CLOSED = "LOSS_CASE_CLOSED"
    LOSS_CASE_REOPENED = "LOSS_CASE_REOPENED"
    LOSS_INVESTIGATION_OPENED = "LOSS_INVESTIGATION_OPENED"
    LOSS_INVESTIGATION_EVIDENCE_ADDED = "LOSS_INVESTIGATION_EVIDENCE_ADDED"
    LOSS_INVESTIGATION_FINDING_ADDED = "LOSS_INVESTIGATION_FINDING_ADDED"
    LOSS_INVESTIGATION_CONCLUDED = "LOSS_INVESTIGATION_CONCLUDED"
    LOSS_ROOT_CAUSE_RECORDED = "LOSS_ROOT_CAUSE_RECORDED"
    LOSS_CORRECTIVE_ACTION_CREATED = "LOSS_CORRECTIVE_ACTION_CREATED"
    LOSS_CORRECTIVE_ACTION_SUBMITTED = "LOSS_CORRECTIVE_ACTION_SUBMITTED"
    LOSS_CORRECTIVE_ACTION_VERIFIED = "LOSS_CORRECTIVE_ACTION_VERIFIED"
    LOSS_VALUED = "LOSS_VALUED"
    LOSS_FINANCE_RECOGNITION_REQUESTED = "LOSS_FINANCE_RECOGNITION_REQUESTED"
    LOSS_DISPOSITION_AUTHORIZED = "LOSS_DISPOSITION_AUTHORIZED"
    LOSS_RECOVERY_RECORDED = "LOSS_RECOVERY_RECORDED"
    LOSS_HIGH_VALUE_DETECTED = "LOSS_HIGH_VALUE_DETECTED"
    YIELD_VARIANCE_DETECTED = "YIELD_VARIANCE_DETECTED"
    YIELD_ALERT_RAISED = "YIELD_ALERT_RAISED"
    LOSS_LOT_BLOCKED = "LOSS_LOT_BLOCKED"
    LOSS_LOT_RECOVERED = "LOSS_LOT_RECOVERED"
    LOSS_DISPOSITION_COMPLETED = "LOSS_DISPOSITION_COMPLETED"
    LOSS_QUALITY_REJECTED = "LOSS_QUALITY_REJECTED"
    LOSS_QUALITY_CONDEMNED = "LOSS_QUALITY_CONDEMNED"
    LOSS_TRANSFER_DIFFERENCE_REGISTERED = "LOSS_TRANSFER_DIFFERENCE_REGISTERED"
    LOSS_TRANSFER_CLAIM_OPENED = "LOSS_TRANSFER_CLAIM_OPENED"
    LOSS_RECOVERY_SUBMITTED = "LOSS_RECOVERY_SUBMITTED"
    LOSS_RECOVERY_APPROVED = "LOSS_RECOVERY_APPROVED"
    LOSS_DISPOSITION_PLANNED = "LOSS_DISPOSITION_PLANNED"


ALL_LOSS_EVENTS = frozenset(
    value for name, value in vars(LossEvents).items()
    if not name.startswith("_") and isinstance(value, str)
)


def _json_value(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def build_loss_event(
    event_name: str,
    *,
    operation_id: str,
    entity_id: str,
    branch_id: str,
    user_id: str,
    warehouse_id: str | None = None,
    source_module: str = "losses",
    **payload,
) -> dict:
    if event_name not in ALL_LOSS_EVENTS:
        raise ValueError(f"Evento Losses desconocido: {event_name}")
    for name, value in {
        "operation_id": operation_id, "entity_id": entity_id,
        "branch_id": branch_id, "user_id": user_id,
    }.items():
        validate_uuidv7(value)
    if warehouse_id is not None:
        validate_uuidv7(warehouse_id)
    event_id = new_uuid()
    if event_id in {operation_id, entity_id} or operation_id == entity_id:
        raise ValueError("event_id, operation_id y entity_id deben ser distintos")
    event = {
        "event_id": event_id,
        "event_name": event_name,
        "operation_id": operation_id,
        "entity_id": entity_id,
        "branch_id": branch_id,
        "warehouse_id": warehouse_id,
        "user_id": user_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_module": source_module,
    }
    event.update({key: _json_value(value) for key, value in payload.items()})
    return event
