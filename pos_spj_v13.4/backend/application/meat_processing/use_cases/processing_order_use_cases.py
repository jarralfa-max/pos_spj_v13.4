"""ProcessingOrder use cases (PROC-6, PROC-22): create → approve → release →
… → close (§12/§13/§14/§35).

Every use case re-validates its permission via an injected
MeatProcessingAuthorizationPolicy; segregation of duties (approver ≠ creator)
is enforced inside the domain entity itself (PROC-2), not re-implemented here.
Mirrors backend/application/inventory/use_cases/adjustment_use_cases.py.
"""

from __future__ import annotations

import json

from backend.application.meat_processing.authorization import MeatProcessingAuthorizationPolicy
from backend.application.meat_processing.execution_context import (
    MeatProcessingExecutionContext,
)
from backend.application.meat_processing.permissions import MeatProcessingPermissions
from backend.application.meat_processing.ports import (
    CostAllocationPort,
    NullCostAllocationPort,
    NullRecipeSnapshotPort,
    RecipeSnapshotPort,
)
from backend.application.meat_processing.result import MeatProcessingResult
from backend.application.meat_processing.use_cases._shared import BLOCKED_QUALITY_STATUSES
from backend.application.meat_processing.use_cases._shared import fail as _fail
from backend.application.meat_processing.use_cases._shared import scope_fail as _scope_fail
from backend.domain.meat_processing.entities.processing_order import ProcessingOrder
from backend.domain.meat_processing.enums import (
    ConsumptionStatus,
    OutputQualityStatus,
    OutputType,
    ProcessingOrderStatus,
    ProcessType,
    YieldStatus,
)
from backend.domain.meat_processing.events import MeatProcessingEvents, build_meat_processing_event
from backend.domain.meat_processing.exceptions import (
    MeatProcessingError,
    MeatProcessingInvariantError,
    MeatProcessingPermissionDeniedError,
)
from backend.domain.meat_processing.policies.order_closing_policy import (
    OrderClosingPolicy,
    ProcessingOrderCloseChecklist,
)
from backend.infrastructure.db.repositories.meat_processing.unit_of_work import (
    MeatProcessingUnitOfWork,
)
from backend.shared.ids import new_uuid

_NEEDS_LOSS_CASE = (YieldStatus.OUT_OF_TOLERANCE, YieldStatus.CRITICAL)
_NON_STOCK_OUTPUT_TYPES = (OutputType.WASTE, OutputType.LOSS)


class CreateProcessingOrderUseCase:
    def __init__(self, authorization: MeatProcessingAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()

    def execute(
        self,
        connection,
        *,
        operation_id: str,
        branch_id: str,
        warehouse_id: str,
        process_type: ProcessType,
        target_product_id: str,
        planned_quantity,
        planned_weight,
        actor_user_id: str,
        production_area_id: str | None = None,
        work_center_id: str | None = None,
        source_type: str | None = None,
        source_reference_id: str | None = None,
        scheduled_start_at=None,
        scheduled_end_at=None,
        priority: int = 0,
        submit_for_approval: bool = True,
        context: MeatProcessingExecutionContext | None = None,
    ) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.ORDER_CREATE)
        except MeatProcessingPermissionDeniedError as exc:
            return _fail(exc, operation_id)
        denied = _scope_fail(context, branch_id, warehouse_id, operation_id)
        if denied is not None:
            return denied
        try:
            with MeatProcessingUnitOfWork(connection) as uow:
                existing = uow.orders.get_by_operation_id(operation_id)
                if existing is not None:
                    return MeatProcessingResult.ok(
                        "Orden ya creada (idempotente)", entity_id=existing.id,
                        operation_id=operation_id, already_processed=True,
                        status=existing.status.value)
                order = ProcessingOrder(
                    id=new_uuid(), operation_id=operation_id, branch_id=branch_id,
                    warehouse_id=warehouse_id, process_type=process_type,
                    target_product_id=target_product_id, created_by_user_id=actor_user_id,
                    planned_quantity=planned_quantity, planned_weight=planned_weight,
                    production_area_id=production_area_id, work_center_id=work_center_id,
                    source_type=source_type, source_reference_id=source_reference_id,
                    scheduled_start_at=scheduled_start_at, scheduled_end_at=scheduled_end_at,
                    priority=priority)
                if submit_for_approval:
                    order.submit_for_approval()
                uow.orders.save(order)
                payload = build_meat_processing_event(
                    MeatProcessingEvents.PROCESSING_ORDER_CREATED, operation_id=operation_id,
                    entity_id=order.id, branch_id=branch_id, warehouse_id=warehouse_id,
                    user_id=actor_user_id, status=order.status.value)
                uow.outbox.enqueue(
                    event_id=payload["event_id"],
                    event_name=MeatProcessingEvents.PROCESSING_ORDER_CREATED,
                    payload_json=json.dumps(payload), operation_id=operation_id)
                uow.audit.record(
                    entity_type="ProcessingOrder", entity_id=order.id, action="CREATED",
                    user_id=actor_user_id, operation_id=operation_id, branch_id=branch_id,
                    warehouse_id=warehouse_id, processing_order_id=order.id)
        except MeatProcessingError as exc:
            return _fail(exc, operation_id)
        return MeatProcessingResult.ok(
            "Orden creada", entity_id=order.id, operation_id=operation_id,
            status=order.status.value)


class ApproveProcessingOrderUseCase:
    def __init__(self, authorization: MeatProcessingAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()

    def execute(
        self,
        connection,
        *,
        order_id: str,
        operation_id: str,
        actor_user_id: str,
        context: MeatProcessingExecutionContext | None = None,
    ) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.ORDER_APPROVE)
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
                if order.status is ProcessingOrderStatus.APPROVED:
                    return MeatProcessingResult.ok(
                        "Orden ya aprobada (idempotente)", entity_id=order.id,
                        operation_id=operation_id, already_processed=True)
                order.approve(actor_user_id=actor_user_id)
                uow.orders.save(order)
                payload = build_meat_processing_event(
                    MeatProcessingEvents.PROCESSING_ORDER_APPROVED, operation_id=operation_id,
                    entity_id=order.id, branch_id=order.branch_id,
                    warehouse_id=order.warehouse_id, user_id=actor_user_id)
                uow.outbox.enqueue(
                    event_id=payload["event_id"],
                    event_name=MeatProcessingEvents.PROCESSING_ORDER_APPROVED,
                    payload_json=json.dumps(payload), operation_id=operation_id)
                uow.audit.record(
                    entity_type="ProcessingOrder", entity_id=order.id, action="APPROVED",
                    user_id=actor_user_id, operation_id=operation_id, branch_id=order.branch_id,
                    warehouse_id=order.warehouse_id, processing_order_id=order.id)
        except MeatProcessingError as exc:
            return _fail(exc, operation_id)
        return MeatProcessingResult.ok(
            "Orden aprobada", entity_id=order.id, operation_id=operation_id)


class ReleaseProcessingOrderUseCase:
    """§14: captures the recipe/cutting-scheme/yield-profile snapshot exactly
    once, immediately before release, then releases the order."""

    def __init__(
        self,
        authorization: MeatProcessingAuthorizationPolicy | None = None,
        recipe_snapshot_port: RecipeSnapshotPort | None = None,
    ) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()
        self._snapshot_port = recipe_snapshot_port or NullRecipeSnapshotPort()

    def execute(
        self,
        connection,
        *,
        order_id: str,
        operation_id: str,
        actor_user_id: str,
        context: MeatProcessingExecutionContext | None = None,
    ) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.ORDER_RELEASE)
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
                if order.status is ProcessingOrderStatus.RELEASED:
                    return MeatProcessingResult.ok(
                        "Orden ya liberada (idempotente)", entity_id=order.id,
                        operation_id=operation_id, already_processed=True)
                if order.recipe_version_id is None and order.cutting_scheme_version_id is None \
                        and order.yield_profile_version_id is None:
                    snapshot = self._snapshot_port.resolve(
                        target_product_id=order.target_product_id,
                        process_type=order.process_type)
                    if snapshot is not None:
                        order.apply_recipe_snapshot(
                            recipe_version_id=snapshot.recipe_version_id,
                            cutting_scheme_version_id=snapshot.cutting_scheme_version_id,
                            yield_profile_version_id=snapshot.yield_profile_version_id)
                        uow.audit.record(
                            entity_type="ProcessingOrder", entity_id=order.id,
                            action="RECIPE_SNAPSHOT_CAPTURED", user_id=actor_user_id,
                            operation_id=operation_id, after_json=json.dumps(
                                snapshot.to_json_dict()),
                            branch_id=order.branch_id, warehouse_id=order.warehouse_id,
                            processing_order_id=order.id)
                order.release(actor_user_id=actor_user_id)
                uow.orders.save(order)
                payload = build_meat_processing_event(
                    MeatProcessingEvents.PROCESSING_ORDER_RELEASED, operation_id=operation_id,
                    entity_id=order.id, branch_id=order.branch_id,
                    warehouse_id=order.warehouse_id, user_id=actor_user_id)
                uow.outbox.enqueue(
                    event_id=payload["event_id"],
                    event_name=MeatProcessingEvents.PROCESSING_ORDER_RELEASED,
                    payload_json=json.dumps(payload), operation_id=operation_id)
                uow.audit.record(
                    entity_type="ProcessingOrder", entity_id=order.id, action="RELEASED",
                    user_id=actor_user_id, operation_id=operation_id, branch_id=order.branch_id,
                    warehouse_id=order.warehouse_id, processing_order_id=order.id)
        except MeatProcessingError as exc:
            return _fail(exc, operation_id)
        return MeatProcessingResult.ok(
            "Orden liberada", entity_id=order.id, operation_id=operation_id)


def _critical_losses_have_case(uow, reconciliations) -> bool:
    for reconciliation in reconciliations:
        if reconciliation.status not in _NEEDS_LOSS_CASE:
            continue
        entries = uow.audit.list_for_entity("YieldReconciliation", reconciliation.id)
        if not any(entry["action"] == "LOSS_CASE_REQUESTED" for entry in entries):
            return False
    return True


def _inventory_confirmed(consumptions, outputs) -> bool:
    for consumption in consumptions:
        if consumption.status is ConsumptionStatus.POSTED \
                and consumption.inventory_operation_id is None:
            return False
    for output in outputs:
        if output.output_type in _NON_STOCK_OUTPUT_TYPES:
            continue
        if output.quality_status in BLOCKED_QUALITY_STATUSES:
            continue
        if output.inventory_operation_id is None:
            return False
    return True


def _build_close_checklist(uow, order, *, costs_notified: bool) -> ProcessingOrderCloseChecklist:
    """§35: every precondition is derived from what Procesamiento itself
    already knows — no cross-context call is assumed to have silently
    succeeded. Where an integration is still Null-ported (Inventory, Losses),
    the corresponding item honestly stays False until that port actually
    confirms something, so a close never fires ahead of real integration."""
    consumptions = uow.consumptions.list_by_order(order.id)
    outputs = uow.outputs.list_by_order(order.id)
    weighings = uow.weighings.list_by_order(order.id)
    reconciliations = uow.yield_reconciliations.list_by_order(order.id)
    return ProcessingOrderCloseChecklist(
        consumptions_posted=all(
            c.status in (ConsumptionStatus.POSTED, ConsumptionStatus.REVERSED)
            for c in consumptions),
        outputs_registered=bool(outputs),
        no_pending_weighings=all(w.stable or w.manual_override for w in weighings),
        quality_resolved=all(
            o.quality_status is not OutputQualityStatus.PENDING_INSPECTION for o in outputs),
        yield_calculated=bool(reconciliations),
        variances_reviewed=bool(reconciliations) and all(
            r.status is YieldStatus.APPROVED for r in reconciliations),
        critical_losses_have_case=_critical_losses_have_case(uow, reconciliations),
        inventory_confirmed=_inventory_confirmed(consumptions, outputs),
        costs_notified=costs_notified)


class CloseProcessingOrderUseCase:
    """§35: the capstone of the order lifecycle — every other bounded-context
    integration this phase depends on (Inventory, Losses, Costos) is checked
    here, honestly, via already-captured local data or a Port+Null call.
    Closing is terminal (§13); reopening a closed order is not a use case,
    only `ProcessingOrder.reverse()` with independent authorization exists
    for that (already built, PROC-2)."""

    def __init__(
        self,
        authorization: MeatProcessingAuthorizationPolicy | None = None,
        cost_allocation_port: CostAllocationPort | None = None,
    ) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()
        self._costing = cost_allocation_port or NullCostAllocationPort()

    def execute(
        self, connection, *, order_id: str, operation_id: str, actor_user_id: str,
        context: MeatProcessingExecutionContext | None = None,
    ) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.ORDER_CLOSE)
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
                if order.status is ProcessingOrderStatus.CLOSED:
                    return MeatProcessingResult.ok(
                        "Orden ya cerrada (idempotente)", entity_id=order.id,
                        operation_id=operation_id, already_processed=True)
                if order.status is not ProcessingOrderStatus.COMPLETED:
                    return MeatProcessingResult.fail(
                        "La orden debe estar completada antes de cerrarse",
                        "ORDER_NOT_COMPLETED", operation_id=operation_id)
                cost_reference = self._costing.request_cost_allocation(
                    operation_id=operation_id, processing_order_id=order.id,
                    process_type=order.process_type)
                checklist = _build_close_checklist(
                    uow, order, costs_notified=cost_reference is not None)
                try:
                    OrderClosingPolicy.ensure_can_close(checklist)
                except MeatProcessingInvariantError:
                    return MeatProcessingResult.fail(
                        "La orden no cumple las condiciones de cierre",
                        "CLOSE_PRECONDITIONS_NOT_MET", operation_id=operation_id,
                        pending_items=list(checklist.pending_items))
                order.close(actor_user_id=actor_user_id)
                uow.orders.save(order)
                uow.audit.record(
                    entity_type="ProcessingOrder", entity_id=order.id, action="CLOSED",
                    user_id=actor_user_id, operation_id=operation_id, branch_id=order.branch_id,
                    warehouse_id=order.warehouse_id, processing_order_id=order.id,
                    after_json=json.dumps({"cost_allocation_reference": cost_reference}))
                payload = build_meat_processing_event(
                    MeatProcessingEvents.PROCESSING_ORDER_CLOSED, operation_id=operation_id,
                    entity_id=order.id, branch_id=order.branch_id,
                    warehouse_id=order.warehouse_id, user_id=actor_user_id)
                uow.outbox.enqueue(
                    event_id=payload["event_id"],
                    event_name=MeatProcessingEvents.PROCESSING_ORDER_CLOSED,
                    payload_json=json.dumps(payload), operation_id=operation_id)
        except MeatProcessingError as exc:
            return _fail(exc, operation_id)
        return MeatProcessingResult.ok(
            "Orden cerrada", entity_id=order.id, operation_id=operation_id,
            cost_allocation_reference=cost_reference)
