"""Execution use cases (PROC-8, §20/§30): start → pause → resume → complete an
order's execution, step tracking within it, and incident reporting. An
incident *can* pause the order (§30) — modeled here as an optional flag rather
than a second call, so the pause and the incident record land atomically.
"""

from __future__ import annotations

import json

from backend.application.meat_processing.authorization import MeatProcessingAuthorizationPolicy
from backend.application.meat_processing.execution_context import (
    MeatProcessingExecutionContext,
)
from backend.application.meat_processing.permissions import MeatProcessingPermissions
from backend.application.meat_processing.result import MeatProcessingResult
from backend.application.meat_processing.use_cases._shared import fail as _fail
from backend.application.meat_processing.use_cases._shared import scope_fail as _scope_fail
from backend.domain.meat_processing.entities.process_execution import ProcessExecution
from backend.domain.meat_processing.entities.process_incident import ProcessIncident
from backend.domain.meat_processing.entities.process_step_execution import ProcessStepExecution
from backend.domain.meat_processing.enums import ExecutionStatus, IncidentType
from backend.domain.meat_processing.events import MeatProcessingEvents, build_meat_processing_event
from backend.domain.meat_processing.exceptions import (
    MeatProcessingError,
    MeatProcessingPermissionDeniedError,
)
from backend.infrastructure.db.repositories.meat_processing.unit_of_work import (
    MeatProcessingUnitOfWork,
)
from backend.shared.ids import new_uuid

_OPEN_EXECUTION_STATUSES = (ExecutionStatus.NOT_STARTED, ExecutionStatus.ACTIVE,
                            ExecutionStatus.PAUSED)


def _current_execution(uow, order_id: str) -> ProcessExecution | None:
    """The most recently created non-terminal execution for this order — this
    simple model assumes one execution in flight per order at a time."""
    candidates = [e for e in uow.executions.list_by_order(order_id)
                  if e.status in _OPEN_EXECUTION_STATUSES]
    return candidates[-1] if candidates else None


def _emit(uow, event_name: str, *, operation_id: str, entity_id: str, order, actor_user_id: str,
          **extra) -> None:
    payload = build_meat_processing_event(
        event_name, operation_id=operation_id, entity_id=entity_id, branch_id=order.branch_id,
        warehouse_id=order.warehouse_id, user_id=actor_user_id, **extra)
    uow.outbox.enqueue(event_id=payload["event_id"], event_name=event_name,
                        payload_json=json.dumps(payload), operation_id=operation_id)


class StartProcessExecutionUseCase:
    def __init__(self, authorization: MeatProcessingAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()

    def execute(
        self, connection, *, order_id: str, operation_id: str, actor_user_id: str,
        work_center_id: str | None = None, context: MeatProcessingExecutionContext | None = None,
    ) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.ORDER_START)
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
                existing = _current_execution(uow, order_id)
                if existing is not None and existing.status is ExecutionStatus.ACTIVE:
                    return MeatProcessingResult.ok(
                        "La orden ya está en ejecución (idempotente)", entity_id=existing.id,
                        operation_id=operation_id, already_processed=True)
                execution = ProcessExecution(
                    id=new_uuid(), operation_id=operation_id, processing_order_id=order_id,
                    work_center_id=work_center_id)
                execution.start()
                order.start(actor_user_id=actor_user_id)
                uow.executions.save(execution)
                uow.orders.save(order)
                _emit(uow, MeatProcessingEvents.PROCESSING_ORDER_STARTED,
                      operation_id=operation_id, entity_id=order.id, order=order,
                      actor_user_id=actor_user_id)
        except MeatProcessingError as exc:
            return _fail(exc, operation_id)
        return MeatProcessingResult.ok(
            "Ejecución iniciada", entity_id=execution.id, operation_id=operation_id)


class PauseProcessExecutionUseCase:
    def __init__(self, authorization: MeatProcessingAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()

    def execute(
        self, connection, *, order_id: str, operation_id: str, actor_user_id: str,
        context: MeatProcessingExecutionContext | None = None,
    ) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.ORDER_PAUSE)
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
                execution = _current_execution(uow, order_id)
                if execution is None:
                    return MeatProcessingResult.fail(
                        "No hay una ejecución activa", "EXECUTION_NOT_FOUND",
                        operation_id=operation_id)
                if execution.status is ExecutionStatus.PAUSED:
                    return MeatProcessingResult.ok(
                        "Ya está pausada (idempotente)", entity_id=execution.id,
                        operation_id=operation_id, already_processed=True)
                execution.pause()
                order.pause()
                uow.executions.save(execution)
                uow.orders.save(order)
                _emit(uow, MeatProcessingEvents.PROCESSING_ORDER_PAUSED,
                      operation_id=operation_id, entity_id=order.id, order=order,
                      actor_user_id=actor_user_id)
        except MeatProcessingError as exc:
            return _fail(exc, operation_id)
        return MeatProcessingResult.ok(
            "Ejecución pausada", entity_id=execution.id, operation_id=operation_id)


class ResumeProcessExecutionUseCase:
    def __init__(self, authorization: MeatProcessingAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()

    def execute(
        self, connection, *, order_id: str, operation_id: str, actor_user_id: str,
        context: MeatProcessingExecutionContext | None = None,
    ) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.ORDER_RESUME)
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
                execution = _current_execution(uow, order_id)
                if execution is None:
                    return MeatProcessingResult.fail(
                        "No hay una ejecución pausada", "EXECUTION_NOT_FOUND",
                        operation_id=operation_id)
                if execution.status is ExecutionStatus.ACTIVE:
                    return MeatProcessingResult.ok(
                        "Ya está en ejecución (idempotente)", entity_id=execution.id,
                        operation_id=operation_id, already_processed=True)
                execution.resume()
                order.resume()
                uow.executions.save(execution)
                uow.orders.save(order)
                _emit(uow, MeatProcessingEvents.PROCESSING_ORDER_RESUMED,
                      operation_id=operation_id, entity_id=order.id, order=order,
                      actor_user_id=actor_user_id)
        except MeatProcessingError as exc:
            return _fail(exc, operation_id)
        return MeatProcessingResult.ok(
            "Ejecución reanudada", entity_id=execution.id, operation_id=operation_id)


class CompleteProcessExecutionUseCase:
    def __init__(self, authorization: MeatProcessingAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()

    def execute(
        self, connection, *, order_id: str, operation_id: str, actor_user_id: str,
        context: MeatProcessingExecutionContext | None = None,
    ) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.ORDER_COMPLETE)
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
                execution = _current_execution(uow, order_id)
                if execution is not None and execution.status is ExecutionStatus.COMPLETED:
                    return MeatProcessingResult.ok(
                        "Ya estaba completada (idempotente)", entity_id=execution.id,
                        operation_id=operation_id, already_processed=True)
                if execution is not None:
                    execution.complete()
                    uow.executions.save(execution)
                order.complete(actor_user_id=actor_user_id)
                uow.orders.save(order)
                _emit(uow, MeatProcessingEvents.PROCESSING_ORDER_COMPLETED,
                      operation_id=operation_id, entity_id=order.id, order=order,
                      actor_user_id=actor_user_id)
        except MeatProcessingError as exc:
            return _fail(exc, operation_id)
        return MeatProcessingResult.ok(
            "Orden completada", entity_id=order.id, operation_id=operation_id)


class StartProcessStepUseCase:
    def __init__(self, authorization: MeatProcessingAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()

    def execute(
        self, connection, *, process_execution_id: str, operation_id: str, step_name: str,
        actor_user_id: str, sequence: int = 0,
        context: MeatProcessingExecutionContext | None = None,
    ) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.ORDER_START)
        except MeatProcessingPermissionDeniedError as exc:
            return _fail(exc, operation_id)
        try:
            with MeatProcessingUnitOfWork(connection) as uow:
                execution = uow.executions.get(process_execution_id)
                if execution is None:
                    return MeatProcessingResult.fail(
                        "Ejecución no encontrada", "EXECUTION_NOT_FOUND",
                        operation_id=operation_id)
                order = uow.orders.get(execution.processing_order_id)
                denied = _scope_fail(context, order.branch_id, order.warehouse_id, operation_id)
                if denied is not None:
                    return denied
                step = ProcessStepExecution(
                    id=new_uuid(), operation_id=operation_id,
                    process_execution_id=process_execution_id, step_name=step_name,
                    sequence=sequence)
                step.start()
                uow.steps.save(step)
        except MeatProcessingError as exc:
            return _fail(exc, operation_id)
        return MeatProcessingResult.ok(
            "Paso iniciado", entity_id=step.id, operation_id=operation_id)


class CompleteProcessStepUseCase:
    def __init__(self, authorization: MeatProcessingAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()

    def execute(
        self, connection, *, step_id: str, operation_id: str, actor_user_id: str,
    ) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.ORDER_COMPLETE)
        except MeatProcessingPermissionDeniedError as exc:
            return _fail(exc, operation_id)
        try:
            with MeatProcessingUnitOfWork(connection) as uow:
                step = uow.steps.get(step_id)
                if step is None:
                    return MeatProcessingResult.fail(
                        "Paso no encontrado", "STEP_NOT_FOUND", operation_id=operation_id)
                if step.status is ExecutionStatus.COMPLETED:
                    return MeatProcessingResult.ok(
                        "Paso ya completado (idempotente)", entity_id=step.id,
                        operation_id=operation_id, already_processed=True)
                step.complete()
                uow.steps.save(step)
        except MeatProcessingError as exc:
            return _fail(exc, operation_id)
        return MeatProcessingResult.ok(
            "Paso completado", entity_id=step.id, operation_id=operation_id)


class ReportProcessIncidentUseCase:
    """§30: an incident can pause the order. `pause_order=True` does both in
    one transaction instead of requiring a second call."""

    def __init__(self, authorization: MeatProcessingAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()

    def execute(
        self, connection, *, order_id: str, operation_id: str, incident_type: IncidentType,
        description: str, actor_user_id: str, process_execution_id: str | None = None,
        pause_order: bool = False, context: MeatProcessingExecutionContext | None = None,
    ) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.INCIDENT_REPORT)
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
                incident = ProcessIncident(
                    id=new_uuid(), operation_id=operation_id, processing_order_id=order_id,
                    incident_type=incident_type, reported_by_user_id=actor_user_id,
                    description=description, process_execution_id=process_execution_id)
                uow.incidents.save(incident)
                if pause_order:
                    execution = _current_execution(uow, order_id)
                    if execution is not None and execution.status is ExecutionStatus.ACTIVE:
                        execution.pause()
                        uow.executions.save(execution)
                    if order.status.value == "IN_PROGRESS":
                        order.pause()
                        uow.orders.save(order)
                _emit(uow, MeatProcessingEvents.PROCESSING_INCIDENT_REPORTED,
                      operation_id=operation_id, entity_id=incident.id, order=order,
                      actor_user_id=actor_user_id, incident_type=incident_type.value)
                uow.audit.record(
                    entity_type="ProcessIncident", entity_id=incident.id, action="REPORTED",
                    user_id=actor_user_id, operation_id=operation_id, branch_id=order.branch_id,
                    warehouse_id=order.warehouse_id, processing_order_id=order_id)
        except MeatProcessingError as exc:
            return _fail(exc, operation_id)
        return MeatProcessingResult.ok(
            "Incidencia reportada", entity_id=incident.id, operation_id=operation_id)


class ResolveProcessIncidentUseCase:
    def __init__(self, authorization: MeatProcessingAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()

    def execute(
        self, connection, *, incident_id: str, operation_id: str, actor_user_id: str,
        resolution_notes: str = "",
    ) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.INCIDENT_RESOLVE)
        except MeatProcessingPermissionDeniedError as exc:
            return _fail(exc, operation_id)
        try:
            with MeatProcessingUnitOfWork(connection) as uow:
                incident = uow.incidents.get(incident_id)
                if incident is None:
                    return MeatProcessingResult.fail(
                        "Incidencia no encontrada", "INCIDENT_NOT_FOUND",
                        operation_id=operation_id)
                if incident.status.value == "RESOLVED":
                    return MeatProcessingResult.ok(
                        "Incidencia ya resuelta (idempotente)", entity_id=incident.id,
                        operation_id=operation_id, already_processed=True)
                incident.resolve(actor_user_id=actor_user_id, resolution_notes=resolution_notes)
                uow.incidents.save(incident)
        except MeatProcessingError as exc:
            return _fail(exc, operation_id)
        return MeatProcessingResult.ok(
            "Incidencia resuelta", entity_id=incident.id, operation_id=operation_id)
