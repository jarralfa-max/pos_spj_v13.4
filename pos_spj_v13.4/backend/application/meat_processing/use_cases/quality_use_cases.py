"""Quality use cases (PROC-16, §28/§44). No new domain — `OutputQualityStatus`
and `ProcessOutput.mark_quality_status()` (a deliberate "dumb setter") already
existed since PROC-2. Procesamiento solicita inspección and records what
Calidad decided; it never makes the decision itself — that's the boundary
`RecordQualityDecisionUseCase` exists to respect, not to blur.
"""

from __future__ import annotations

import json

from backend.application.meat_processing.authorization import MeatProcessingAuthorizationPolicy
from backend.application.meat_processing.execution_context import (
    MeatProcessingExecutionContext,
)
from backend.application.meat_processing.permissions import MeatProcessingPermissions
from backend.application.meat_processing.ports import (
    NullQualityInspectionPort,
    QualityInspectionPort,
)
from backend.application.meat_processing.result import MeatProcessingResult
from backend.application.meat_processing.use_cases._shared import BLOCKED_QUALITY_STATUSES
from backend.application.meat_processing.use_cases._shared import fail as _fail
from backend.application.meat_processing.use_cases._shared import scope_fail as _scope_fail
from backend.domain.meat_processing.enums import OutputQualityStatus, ProcessingOrderStatus
from backend.domain.meat_processing.events import MeatProcessingEvents, build_meat_processing_event
from backend.domain.meat_processing.exceptions import (
    MeatProcessingError,
    MeatProcessingPermissionDeniedError,
)
from backend.infrastructure.db.repositories.meat_processing.unit_of_work import (
    MeatProcessingUnitOfWork,
)

_ORDER_IN_FLIGHT = (ProcessingOrderStatus.IN_PROGRESS, ProcessingOrderStatus.PARTIALLY_COMPLETED)


class RequestQualityInspectionUseCase:
    def __init__(
        self,
        authorization: MeatProcessingAuthorizationPolicy | None = None,
        quality_port: QualityInspectionPort | None = None,
    ) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()
        self._quality = quality_port or NullQualityInspectionPort()

    def execute(
        self, connection, *, output_id: str, operation_id: str, actor_user_id: str,
        context: MeatProcessingExecutionContext | None = None,
    ) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.QUALITY_REQUEST_INSPECTION)
        except MeatProcessingPermissionDeniedError as exc:
            return _fail(exc, operation_id)
        try:
            with MeatProcessingUnitOfWork(connection) as uow:
                output = uow.outputs.get(output_id)
                if output is None:
                    return MeatProcessingResult.fail(
                        "Output no encontrado", "OUTPUT_NOT_FOUND", operation_id=operation_id)
                order = uow.orders.get(output.processing_order_id)
                denied = _scope_fail(context, order.branch_id, order.warehouse_id, operation_id)
                if denied is not None:
                    return denied
                inspection_request_id = self._quality.request_inspection(
                    operation_id=operation_id, process_output_id=output.id,
                    product_id=output.product_id, lot_id=output.lot_id)
                if inspection_request_id is None:
                    return MeatProcessingResult.fail(
                        "Calidad aún no confirma la solicitud", "QUALITY_INTEGRATION_PENDING",
                        operation_id=operation_id)
                if order.status in _ORDER_IN_FLIGHT:
                    order.request_quality_review()
                    uow.orders.save(order)
                uow.audit.record(
                    entity_type="ProcessOutput", entity_id=output.id,
                    action="QUALITY_INSPECTION_REQUESTED", user_id=actor_user_id,
                    operation_id=operation_id, after_json=json.dumps(
                        {"inspection_request_id": inspection_request_id}),
                    branch_id=order.branch_id, warehouse_id=order.warehouse_id,
                    processing_order_id=order.id)
                payload = build_meat_processing_event(
                    MeatProcessingEvents.PROCESSING_QUALITY_REQUESTED, operation_id=operation_id,
                    entity_id=output.id, branch_id=order.branch_id,
                    warehouse_id=order.warehouse_id, user_id=actor_user_id,
                    inspection_request_id=inspection_request_id)
                uow.outbox.enqueue(
                    event_id=payload["event_id"],
                    event_name=MeatProcessingEvents.PROCESSING_QUALITY_REQUESTED,
                    payload_json=json.dumps(payload), operation_id=operation_id)
        except MeatProcessingError as exc:
            return _fail(exc, operation_id)
        return MeatProcessingResult.ok(
            "Inspección solicitada", entity_id=output.id, operation_id=operation_id,
            inspection_request_id=inspection_request_id)


class RecordQualityDecisionUseCase:
    """Records a decision Calidad already made — it never classifies or
    liberates on Procesamiento's own authority (§28)."""

    def __init__(self, authorization: MeatProcessingAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()

    def execute(
        self, connection, *, output_id: str, operation_id: str,
        decision: OutputQualityStatus, actor_user_id: str,
        context: MeatProcessingExecutionContext | None = None,
    ) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.QUALITY_RECORD_DECISION)
        except MeatProcessingPermissionDeniedError as exc:
            return _fail(exc, operation_id)
        try:
            with MeatProcessingUnitOfWork(connection) as uow:
                output = uow.outputs.get(output_id)
                if output is None:
                    return MeatProcessingResult.fail(
                        "Output no encontrado", "OUTPUT_NOT_FOUND", operation_id=operation_id)
                order = uow.orders.get(output.processing_order_id)
                denied = _scope_fail(context, order.branch_id, order.warehouse_id, operation_id)
                if denied is not None:
                    return denied
                if output.quality_status == decision:
                    return MeatProcessingResult.ok(
                        "Decisión ya registrada (idempotente)", entity_id=output.id,
                        operation_id=operation_id, already_processed=True)
                output.mark_quality_status(decision)
                uow.outputs.save(output)
                uow.audit.record(
                    entity_type="ProcessOutput", entity_id=output.id,
                    action="QUALITY_DECISION_RECORDED", user_id=actor_user_id,
                    operation_id=operation_id, after_json=json.dumps({"decision": decision.value}),
                    branch_id=order.branch_id, warehouse_id=order.warehouse_id,
                    processing_order_id=order.id)
                event_name = (
                    MeatProcessingEvents.PROCESSING_OUTPUT_RELEASED
                    if decision is OutputQualityStatus.RELEASED
                    else MeatProcessingEvents.PROCESSING_OUTPUT_BLOCKED)
                payload = build_meat_processing_event(
                    event_name, operation_id=operation_id, entity_id=output.id,
                    branch_id=order.branch_id, warehouse_id=order.warehouse_id,
                    user_id=actor_user_id, decision=decision.value)
                uow.outbox.enqueue(
                    event_id=payload["event_id"], event_name=event_name,
                    payload_json=json.dumps(payload), operation_id=operation_id)
        except MeatProcessingError as exc:
            return _fail(exc, operation_id)
        return MeatProcessingResult.ok(
            "Decisión de calidad registrada", entity_id=output.id, operation_id=operation_id,
            blocked=decision in BLOCKED_QUALITY_STATUSES)
