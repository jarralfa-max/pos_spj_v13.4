"""Rework use cases (PROC-17, §29): Producto bloqueado → Crear → Aprobar →
Ejecutar → Completar → Cerrar. "No modificar silenciosamente la orden
original" — `StartReworkExecutionUseCase` creates a brand-new ProcessingOrder
to run the rework through the same núcleo productivo (§1); the source order
and its blocked output are never touched.
"""

from __future__ import annotations

import json

from backend.application.meat_processing.authorization import MeatProcessingAuthorizationPolicy
from backend.application.meat_processing.execution_context import (
    MeatProcessingExecutionContext,
)
from backend.application.meat_processing.permissions import MeatProcessingPermissions
from backend.application.meat_processing.result import MeatProcessingResult
from backend.application.meat_processing.use_cases._shared import BLOCKED_QUALITY_STATUSES
from backend.application.meat_processing.use_cases._shared import fail as _fail
from backend.application.meat_processing.use_cases._shared import scope_fail as _scope_fail
from backend.domain.meat_processing.entities.processing_order import ProcessingOrder
from backend.domain.meat_processing.entities.rework_order import ReworkOrder
from backend.domain.meat_processing.enums import ProcessType, ReworkOrderStatus, ReworkOrigin
from backend.domain.meat_processing.events import MeatProcessingEvents, build_meat_processing_event
from backend.domain.meat_processing.exceptions import (
    MeatProcessingError,
    MeatProcessingInvariantError,
    MeatProcessingPermissionDeniedError,
)
from backend.infrastructure.db.repositories.meat_processing.unit_of_work import (
    MeatProcessingUnitOfWork,
)
from backend.shared.ids import new_uuid


class CreateReworkOrderUseCase:
    def __init__(self, authorization: MeatProcessingAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()

    def execute(
        self, connection, *, source_output_id: str, operation_id: str, origin: ReworkOrigin,
        actor_user_id: str, quantity=0, weight=0, reason: str = "",
        context: MeatProcessingExecutionContext | None = None,
    ) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.REWORK_CREATE)
        except MeatProcessingPermissionDeniedError as exc:
            return _fail(exc, operation_id)
        try:
            with MeatProcessingUnitOfWork(connection) as uow:
                output = uow.outputs.get(source_output_id)
                if output is None:
                    return MeatProcessingResult.fail(
                        "Output no encontrado", "OUTPUT_NOT_FOUND", operation_id=operation_id)
                order = uow.orders.get(output.processing_order_id)
                denied = _scope_fail(context, order.branch_id, order.warehouse_id, operation_id)
                if denied is not None:
                    return denied
                if output.quality_status not in BLOCKED_QUALITY_STATUSES:
                    return MeatProcessingResult.fail(
                        "El output no está bloqueado; no requiere reproceso",
                        "OUTPUT_NOT_BLOCKED", operation_id=operation_id)
                rework = ReworkOrder(
                    id=new_uuid(), operation_id=operation_id, source_output_id=source_output_id,
                    product_id=output.product_id, origin=origin,
                    created_by_user_id=actor_user_id,
                    quantity=quantity or output.quantity, weight=weight or output.weight,
                    reason=reason)
                uow.rework_orders.save(rework)
                uow.audit.record(
                    entity_type="ReworkOrder", entity_id=rework.id, action="CREATED",
                    user_id=actor_user_id, operation_id=operation_id, branch_id=order.branch_id,
                    warehouse_id=order.warehouse_id, processing_order_id=order.id)
                payload = build_meat_processing_event(
                    MeatProcessingEvents.PROCESSING_REWORK_CREATED, operation_id=operation_id,
                    entity_id=rework.id, branch_id=order.branch_id,
                    warehouse_id=order.warehouse_id, user_id=actor_user_id,
                    origin=origin.value)
                uow.outbox.enqueue(
                    event_id=payload["event_id"],
                    event_name=MeatProcessingEvents.PROCESSING_REWORK_CREATED,
                    payload_json=json.dumps(payload), operation_id=operation_id)
        except MeatProcessingError as exc:
            return _fail(exc, operation_id)
        return MeatProcessingResult.ok(
            "Reproceso creado", entity_id=rework.id, operation_id=operation_id)


class ApproveReworkOrderUseCase:
    def __init__(self, authorization: MeatProcessingAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()

    def execute(
        self, connection, *, rework_order_id: str, operation_id: str, actor_user_id: str,
    ) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.REWORK_APPROVE)
        except MeatProcessingPermissionDeniedError as exc:
            return _fail(exc, operation_id)
        try:
            with MeatProcessingUnitOfWork(connection) as uow:
                rework = uow.rework_orders.get(rework_order_id)
                if rework is None:
                    return MeatProcessingResult.fail(
                        "Reproceso no encontrado", "REWORK_NOT_FOUND", operation_id=operation_id)
                if rework.status is ReworkOrderStatus.APPROVED:
                    return MeatProcessingResult.ok(
                        "Reproceso ya aprobado (idempotente)", entity_id=rework.id,
                        operation_id=operation_id, already_processed=True)
                rework.approve(actor_user_id=actor_user_id)
                uow.rework_orders.save(rework)
        except MeatProcessingError as exc:
            return _fail(exc, operation_id)
        return MeatProcessingResult.ok(
            "Reproceso aprobado", entity_id=rework.id, operation_id=operation_id)


class StartReworkExecutionUseCase:
    def __init__(self, authorization: MeatProcessingAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()

    def execute(
        self, connection, *, rework_order_id: str, operation_id: str, branch_id: str,
        warehouse_id: str, process_type: ProcessType, actor_user_id: str,
        context: MeatProcessingExecutionContext | None = None,
    ) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.REWORK_EXECUTE)
        except MeatProcessingPermissionDeniedError as exc:
            return _fail(exc, operation_id)
        try:
            with MeatProcessingUnitOfWork(connection) as uow:
                rework = uow.rework_orders.get(rework_order_id)
                if rework is None:
                    return MeatProcessingResult.fail(
                        "Reproceso no encontrado", "REWORK_NOT_FOUND", operation_id=operation_id)
                denied = _scope_fail(context, branch_id, warehouse_id, operation_id)
                if denied is not None:
                    return denied
                if rework.status is ReworkOrderStatus.IN_PROGRESS:
                    return MeatProcessingResult.ok(
                        "Reproceso ya en ejecución (idempotente)", entity_id=rework.id,
                        operation_id=operation_id, already_processed=True,
                        processing_order_id=rework.processing_order_id)
                new_order = ProcessingOrder(
                    id=new_uuid(), operation_id=new_uuid(), branch_id=branch_id,
                    warehouse_id=warehouse_id, process_type=process_type,
                    target_product_id=rework.product_id, created_by_user_id=actor_user_id,
                    planned_quantity=rework.quantity, planned_weight=rework.weight,
                    source_type="REWORK_ORDER", source_reference_id=rework.id)
                uow.orders.save(new_order)
                rework.start_execution(processing_order_id=new_order.id)
                uow.rework_orders.save(rework)
        except MeatProcessingError as exc:
            return _fail(exc, operation_id)
        return MeatProcessingResult.ok(
            "Ejecución de reproceso iniciada", entity_id=rework.id, operation_id=operation_id,
            processing_order_id=new_order.id)


class CompleteReworkOrderUseCase:
    def __init__(self, authorization: MeatProcessingAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()

    def execute(
        self, connection, *, rework_order_id: str, operation_id: str, actor_user_id: str,
    ) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.REWORK_EXECUTE)
        except MeatProcessingPermissionDeniedError as exc:
            return _fail(exc, operation_id)
        try:
            with MeatProcessingUnitOfWork(connection) as uow:
                rework = uow.rework_orders.get(rework_order_id)
                if rework is None:
                    return MeatProcessingResult.fail(
                        "Reproceso no encontrado", "REWORK_NOT_FOUND", operation_id=operation_id)
                if rework.status is ReworkOrderStatus.COMPLETED:
                    return MeatProcessingResult.ok(
                        "Reproceso ya completado (idempotente)", entity_id=rework.id,
                        operation_id=operation_id, already_processed=True)
                # branch_id/warehouse_id aren't on the rework order itself —
                # they live on the new ProcessingOrder it started (§29:
                # complete() requires IN_PROGRESS, so processing_order_id is
                # always set by now).
                new_order = uow.orders.get(rework.processing_order_id)
                rework.complete()
                uow.rework_orders.save(rework)
                payload = build_meat_processing_event(
                    MeatProcessingEvents.PROCESSING_REWORK_COMPLETED, operation_id=operation_id,
                    entity_id=rework.id, branch_id=new_order.branch_id,
                    warehouse_id=new_order.warehouse_id, user_id=actor_user_id)
                uow.outbox.enqueue(
                    event_id=payload["event_id"],
                    event_name=MeatProcessingEvents.PROCESSING_REWORK_COMPLETED,
                    payload_json=json.dumps(payload), operation_id=operation_id)
        except MeatProcessingError as exc:
            return _fail(exc, operation_id)
        return MeatProcessingResult.ok(
            "Reproceso completado", entity_id=rework.id, operation_id=operation_id)


class CloseReworkOrderUseCase:
    def __init__(self, authorization: MeatProcessingAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()

    def execute(
        self, connection, *, rework_order_id: str, operation_id: str, actor_user_id: str,
    ) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.REWORK_CLOSE)
        except MeatProcessingPermissionDeniedError as exc:
            return _fail(exc, operation_id)
        try:
            with MeatProcessingUnitOfWork(connection) as uow:
                rework = uow.rework_orders.get(rework_order_id)
                if rework is None:
                    return MeatProcessingResult.fail(
                        "Reproceso no encontrado", "REWORK_NOT_FOUND", operation_id=operation_id)
                if rework.status is ReworkOrderStatus.CLOSED:
                    return MeatProcessingResult.ok(
                        "Reproceso ya cerrado (idempotente)", entity_id=rework.id,
                        operation_id=operation_id, already_processed=True)
                rework.close()
                uow.rework_orders.save(rework)
        except MeatProcessingError as exc:
            return _fail(exc, operation_id)
        return MeatProcessingResult.ok(
            "Reproceso cerrado", entity_id=rework.id, operation_id=operation_id)
