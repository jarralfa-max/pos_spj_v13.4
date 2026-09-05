"""Yield reconciliation use cases (PROC-14, §26) and the outbound loss-case
request (PROC-15, §27). Esperado/Real/Tolerancias are already the
`YieldReconciliation` entity's own fields (PROC-2); this layer adds what was
missing: a *standalone* reconciliation (decoupled from output capture — for
outputs that were captured incrementally via PROC-10 rather than all at once
via PROC-11/12's `RecordProcessOutputsUseCase`), the review/approval step
(`YieldReconciliation.approve()` existed since PROC-2 with no caller until
now), and requesting a Mermas/Losses case when the variance is out of
tolerance.
"""

from __future__ import annotations

import json

from backend.application.meat_processing.authorization import MeatProcessingAuthorizationPolicy
from backend.application.meat_processing.execution_context import (
    MeatProcessingExecutionContext,
)
from backend.application.meat_processing.permissions import MeatProcessingPermissions
from backend.application.meat_processing.ports import LossCaseRequestPort, NullLossCaseRequestPort
from backend.application.meat_processing.result import MeatProcessingResult
from backend.application.meat_processing.use_cases._shared import fail as _fail
from backend.application.meat_processing.use_cases._shared import scope_fail as _scope_fail
from backend.application.meat_processing.use_cases._shared import (
    summarize_outputs_by_type as _summarize_outputs_by_type,
)
from backend.domain.meat_processing.entities.yield_reconciliation import YieldReconciliation
from backend.domain.meat_processing.enums import YieldStatus
from backend.domain.meat_processing.events import MeatProcessingEvents, build_meat_processing_event
from backend.domain.meat_processing.exceptions import (
    MeatProcessingError,
    MeatProcessingPermissionDeniedError,
)
from backend.domain.meat_processing.policies.yield_reconciliation_policy import (
    YieldReconciliationPolicy,
)
from backend.infrastructure.db.repositories.meat_processing.unit_of_work import (
    MeatProcessingUnitOfWork,
)
from backend.shared.ids import new_uuid

_OUT_OF_TOLERANCE = (YieldStatus.OUT_OF_TOLERANCE, YieldStatus.CRITICAL)


class ReconcileYieldUseCase:
    """Builds a YieldReconciliation from outputs already captured earlier
    (via CaptureProcessOutputUseCase, PROC-10) instead of requiring them to be
    captured atomically in the same call (that's what RecordProcessOutputsUseCase,
    PROC-11/12, is for)."""

    def __init__(self, authorization: MeatProcessingAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()

    def execute(
        self, connection, *, order_id: str, operation_id: str, actor_user_id: str,
        input_quantity, input_weight, expected_output_quantity, expected_output_weight,
        warning_pct, tolerance_pct, critical_pct, processing_batch_id: str | None = None,
        context: MeatProcessingExecutionContext | None = None,
    ) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.YIELD_REVIEW)
        except MeatProcessingPermissionDeniedError as exc:
            return _fail(exc, operation_id)
        try:
            with MeatProcessingUnitOfWork(connection) as uow:
                order = uow.orders.get(order_id)
                if order is None:
                    return MeatProcessingResult.fail(
                        "Orden no encontrada", "ORDER_NOT_FOUND", operation_id=operation_id)
                denied = _scope_fail(context, order.branch_id, order.warehouse_id, operation_id)
                if denied is not None:
                    return denied
                outputs = (uow.outputs.list_by_batch(processing_batch_id)
                           if processing_batch_id else uow.outputs.list_by_order(order_id))
                if not outputs:
                    return MeatProcessingResult.fail(
                        "La orden no tiene outputs capturados", "NO_OUTPUTS",
                        operation_id=operation_id)
                totals = _summarize_outputs_by_type(outputs)
                reconciliation = YieldReconciliation(
                    id=new_uuid(), operation_id=operation_id, processing_order_id=order_id,
                    processing_batch_id=processing_batch_id, input_quantity=input_quantity,
                    input_weight=input_weight, expected_output_quantity=expected_output_quantity,
                    expected_output_weight=expected_output_weight,
                    actual_output_quantity=totals["actual_quantity"],
                    actual_output_weight=totals["actual_weight"],
                    co_product_weight=totals["co_product_weight"],
                    by_product_weight=totals["by_product_weight"],
                    waste_weight=totals["waste_weight"], tolerance_pct=tolerance_pct)
                status = YieldReconciliationPolicy.classify(
                    reconciliation.variance_pct, warning_pct=warning_pct,
                    tolerance_pct=tolerance_pct, critical_pct=critical_pct)
                reconciliation.apply_classification(status)
                uow.yield_reconciliations.save(reconciliation)
                payload = build_meat_processing_event(
                    MeatProcessingEvents.PROCESSING_YIELD_CALCULATED, operation_id=operation_id,
                    entity_id=reconciliation.id, branch_id=order.branch_id,
                    warehouse_id=order.warehouse_id, user_id=actor_user_id, status=status.value)
                uow.outbox.enqueue(
                    event_id=payload["event_id"],
                    event_name=MeatProcessingEvents.PROCESSING_YIELD_CALCULATED,
                    payload_json=json.dumps(payload), operation_id=operation_id)
                if status in _OUT_OF_TOLERANCE:
                    alert_operation_id = new_uuid()
                    alert_payload = build_meat_processing_event(
                        MeatProcessingEvents.PROCESSING_YIELD_OUT_OF_TOLERANCE,
                        operation_id=alert_operation_id, entity_id=reconciliation.id,
                        branch_id=order.branch_id, warehouse_id=order.warehouse_id,
                        user_id=actor_user_id, status=status.value)
                    uow.outbox.enqueue(
                        event_id=alert_payload["event_id"],
                        event_name=MeatProcessingEvents.PROCESSING_YIELD_OUT_OF_TOLERANCE,
                        payload_json=json.dumps(alert_payload), operation_id=alert_operation_id)
        except MeatProcessingError as exc:
            return _fail(exc, operation_id)
        return MeatProcessingResult.ok(
            "Rendimiento conciliado", entity_id=reconciliation.id, operation_id=operation_id,
            yield_status=reconciliation.status.value)


class ApproveYieldReconciliationUseCase:
    def __init__(self, authorization: MeatProcessingAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()

    def execute(
        self, connection, *, reconciliation_id: str, operation_id: str, actor_user_id: str,
    ) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.YIELD_APPROVE)
        except MeatProcessingPermissionDeniedError as exc:
            return _fail(exc, operation_id)
        try:
            with MeatProcessingUnitOfWork(connection) as uow:
                reconciliation = uow.yield_reconciliations.get(reconciliation_id)
                if reconciliation is None:
                    return MeatProcessingResult.fail(
                        "Rendimiento no encontrado", "RECONCILIATION_NOT_FOUND",
                        operation_id=operation_id)
                if reconciliation.status is YieldStatus.APPROVED:
                    return MeatProcessingResult.ok(
                        "Rendimiento ya aprobado (idempotente)", entity_id=reconciliation.id,
                        operation_id=operation_id, already_processed=True)
                reconciliation.approve(actor_user_id=actor_user_id)
                uow.yield_reconciliations.save(reconciliation)
                order = uow.orders.get(reconciliation.processing_order_id)
                payload = build_meat_processing_event(
                    MeatProcessingEvents.PROCESSING_YIELD_APPROVED, operation_id=operation_id,
                    entity_id=reconciliation.id, branch_id=order.branch_id,
                    warehouse_id=order.warehouse_id, user_id=actor_user_id)
                uow.outbox.enqueue(
                    event_id=payload["event_id"],
                    event_name=MeatProcessingEvents.PROCESSING_YIELD_APPROVED,
                    payload_json=json.dumps(payload), operation_id=operation_id)
        except MeatProcessingError as exc:
            return _fail(exc, operation_id)
        return MeatProcessingResult.ok(
            "Rendimiento aprobado", entity_id=reconciliation.id, operation_id=operation_id)


class RequestLossCaseForYieldVarianceUseCase:
    """§27: only fires when the reconciliation is OUT_OF_TOLERANCE/CRITICAL —
    Procesamiento never classifies the loss itself, it only requests one from
    Mermas/Losses via `LossCaseRequestPort`, carrying operator/equipment
    context so Losses doesn't have to re-derive it."""

    def __init__(
        self,
        authorization: MeatProcessingAuthorizationPolicy | None = None,
        loss_case_port: LossCaseRequestPort | None = None,
    ) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()
        self._losses = loss_case_port or NullLossCaseRequestPort()

    def execute(
        self, connection, *, reconciliation_id: str, operation_id: str, actor_user_id: str,
        context: MeatProcessingExecutionContext | None = None,
    ) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.REQUEST_LOSS_CASE)
        except MeatProcessingPermissionDeniedError as exc:
            return _fail(exc, operation_id)
        try:
            with MeatProcessingUnitOfWork(connection) as uow:
                reconciliation = uow.yield_reconciliations.get(reconciliation_id)
                if reconciliation is None:
                    return MeatProcessingResult.fail(
                        "Rendimiento no encontrado", "RECONCILIATION_NOT_FOUND",
                        operation_id=operation_id)
                order = uow.orders.get(reconciliation.processing_order_id)
                denied = _scope_fail(context, order.branch_id, order.warehouse_id, operation_id)
                if denied is not None:
                    return denied
                if reconciliation.status not in _OUT_OF_TOLERANCE:
                    return MeatProcessingResult.fail(
                        "El rendimiento no está fuera de tolerancia", "WITHIN_TOLERANCE",
                        operation_id=operation_id)
                if uow.processed_events.was_processed(operation_id):
                    return MeatProcessingResult.ok(
                        "Ya solicitado (idempotente)", operation_id=operation_id,
                        already_processed=True)
                operator_ids = tuple(
                    assignment.user_id for assignment
                    in uow.operator_assignments.list_active_by_order(order.id))
                loss_case_id = self._losses.request_loss_case(
                    operation_id=operation_id, processing_order_id=order.id,
                    product_id=order.target_product_id,
                    expected_weight=reconciliation.expected_output_weight,
                    actual_weight=reconciliation.actual_output_weight,
                    difference_weight=reconciliation.unexplained_difference,
                    process_type=order.process_type,
                    processing_batch_id=reconciliation.processing_batch_id,
                    operator_ids=operator_ids)
                if loss_case_id is None:
                    return MeatProcessingResult.fail(
                        "Mermas aún no confirma el expediente", "LOSSES_INTEGRATION_PENDING",
                        operation_id=operation_id)
                uow.audit.record(
                    entity_type="YieldReconciliation", entity_id=reconciliation.id,
                    action="LOSS_CASE_REQUESTED", user_id=actor_user_id,
                    operation_id=operation_id, after_json=json.dumps({"loss_case_id": loss_case_id}),
                    branch_id=order.branch_id, warehouse_id=order.warehouse_id,
                    processing_order_id=order.id)
                payload = build_meat_processing_event(
                    MeatProcessingEvents.PROCESSING_LOSS_CASE_REQUESTED,
                    operation_id=operation_id, entity_id=reconciliation.id,
                    branch_id=order.branch_id, warehouse_id=order.warehouse_id,
                    user_id=actor_user_id, loss_case_id=loss_case_id)
                uow.outbox.enqueue(
                    event_id=payload["event_id"],
                    event_name=MeatProcessingEvents.PROCESSING_LOSS_CASE_REQUESTED,
                    payload_json=json.dumps(payload), operation_id=operation_id)
                uow.processed_events.mark_processed(
                    operation_id, "PROCESSING_LOSS_CASE_REQUESTED", operation_id)
        except MeatProcessingError as exc:
            return _fail(exc, operation_id)
        return MeatProcessingResult.ok(
            "Expediente de merma solicitado", entity_id=loss_case_id, operation_id=operation_id)
