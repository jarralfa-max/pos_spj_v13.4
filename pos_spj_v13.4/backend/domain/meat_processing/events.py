"""Canonical Meat Processing event names and JSON-safe event envelope builder (§60).

Scoped to what the built entities can actually emit: the production plan
lifecycle (PROC-5), the order lifecycle, material consumption, weighing,
output and yield events (PROC-2). Quality/rework/incident/label/notification
events from §60 are added once the phases that build those entities
(PROC-16/17/20) exist — defining event names ahead of any entity that could emit
them would be unused scaffolding.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from backend.shared.ids import new_uuid, validate_uuidv7


class MeatProcessingEvents:
    PRODUCTION_PLAN_CREATED = "PRODUCTION_PLAN_CREATED"
    PRODUCTION_PLAN_APPROVED = "PRODUCTION_PLAN_APPROVED"
    PRODUCTION_PLAN_CANCELLED = "PRODUCTION_PLAN_CANCELLED"
    PRODUCTION_PLAN_LINE_CONVERTED = "PRODUCTION_PLAN_LINE_CONVERTED"
    PRODUCTION_PLAN_CONVERTED = "PRODUCTION_PLAN_CONVERTED"

    PROCESSING_ORDER_CREATED = "PROCESSING_ORDER_CREATED"
    PROCESSING_ORDER_APPROVED = "PROCESSING_ORDER_APPROVED"
    PROCESSING_ORDER_RELEASED = "PROCESSING_ORDER_RELEASED"
    PROCESSING_ORDER_STARTED = "PROCESSING_ORDER_STARTED"
    PROCESSING_ORDER_PAUSED = "PROCESSING_ORDER_PAUSED"
    PROCESSING_ORDER_RESUMED = "PROCESSING_ORDER_RESUMED"
    PROCESSING_ORDER_COMPLETED = "PROCESSING_ORDER_COMPLETED"
    PROCESSING_ORDER_CLOSED = "PROCESSING_ORDER_CLOSED"
    PROCESSING_ORDER_CANCELLED = "PROCESSING_ORDER_CANCELLED"
    PROCESSING_ORDER_REVERSED = "PROCESSING_ORDER_REVERSED"

    PROCESSING_MATERIAL_CONSUMED = "PROCESSING_MATERIAL_CONSUMED"

    PROCESSING_WEIGHT_CAPTURED = "PROCESSING_WEIGHT_CAPTURED"

    PROCESSING_OUTPUT_PRODUCED = "PROCESSING_OUTPUT_PRODUCED"
    PROCESSING_CO_PRODUCT_PRODUCED = "PROCESSING_CO_PRODUCT_PRODUCED"
    PROCESSING_BY_PRODUCT_PRODUCED = "PROCESSING_BY_PRODUCT_PRODUCED"
    PROCESSING_SUBPRODUCT_PRODUCED = "PROCESSING_SUBPRODUCT_PRODUCED"
    PROCESSING_WASTE_RECORDED = "PROCESSING_WASTE_RECORDED"

    PROCESSING_YIELD_CALCULATED = "PROCESSING_YIELD_CALCULATED"
    PROCESSING_YIELD_OUT_OF_TOLERANCE = "PROCESSING_YIELD_OUT_OF_TOLERANCE"


ALL_MEAT_PROCESSING_EVENTS = frozenset(
    value for name, value in vars(MeatProcessingEvents).items()
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


def build_meat_processing_event(
    event_name: str,
    *,
    operation_id: str,
    entity_id: str,
    branch_id: str,
    user_id: str,
    warehouse_id: str | None = None,
    source_module: str = "meat_processing",
    **payload,
) -> dict:
    if event_name not in ALL_MEAT_PROCESSING_EVENTS:
        raise ValueError(f"Evento Meat Processing desconocido: {event_name}")
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
