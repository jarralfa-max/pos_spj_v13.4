"""Preparation use cases (PROC-7, §15/§16/§32): material requirements,
reservation/allocation, operator assignment, and the final "ready to release"
gate. Procesamiento tracks requirements locally and never writes Inventory's
own tables (§39) — reserve()/allocate() record what Procesamiento believes was
granted; a real MaterialAvailabilityPort integration against Inventory is a
later phase.
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
from backend.domain.meat_processing.entities.material_requirement import MaterialRequirement
from backend.domain.meat_processing.entities.operator_assignment import OperatorAssignment
from backend.domain.meat_processing.enums import (
    MaterialRequirementStatus,
    OperatorRole,
    ProcessingOrderStatus,
)
from backend.domain.meat_processing.events import MeatProcessingEvents, build_meat_processing_event
from backend.domain.meat_processing.exceptions import (
    MeatProcessingError,
    MeatProcessingPermissionDeniedError,
)
from backend.infrastructure.db.repositories.meat_processing.unit_of_work import (
    MeatProcessingUnitOfWork,
)
from backend.shared.ids import new_uuid

_UNSATISFIED = (MaterialRequirementStatus.REQUIRED,)


class AddMaterialRequirementUseCase:
    def __init__(self, authorization: MeatProcessingAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()

    def execute(
        self, connection, *, order_id: str, operation_id: str, product_id: str,
        required_quantity, required_weight, actor_user_id: str, unit: str = "unit",
        substitution_allowed: bool = False, quality_required: bool = False,
        lot_required: bool = False, context: MeatProcessingExecutionContext | None = None,
    ) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.MATERIAL_ASSIGN)
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
                existing = next(
                    (r for r in uow.material_requirements.list_by_order(order_id)
                     if r.operation_id == operation_id), None)
                if existing is not None:
                    return MeatProcessingResult.ok(
                        "Requerimiento ya registrado (idempotente)", entity_id=existing.id,
                        operation_id=operation_id, already_processed=True)
                requirement = MaterialRequirement(
                    id=new_uuid(), operation_id=operation_id, processing_order_id=order_id,
                    product_id=product_id, required_quantity=required_quantity,
                    required_weight=required_weight, unit=unit,
                    substitution_allowed=substitution_allowed,
                    quality_required=quality_required, lot_required=lot_required)
                if order.status is ProcessingOrderStatus.APPROVED:
                    order.mark_materials_pending()
                    uow.orders.save(order)
                uow.material_requirements.save(requirement)
                uow.audit.record(
                    entity_type="MaterialRequirement", entity_id=requirement.id,
                    action="CREATED", user_id=actor_user_id, operation_id=operation_id,
                    branch_id=order.branch_id, warehouse_id=order.warehouse_id,
                    processing_order_id=order_id)
        except MeatProcessingError as exc:
            return _fail(exc, operation_id)
        return MeatProcessingResult.ok(
            "Requerimiento registrado", entity_id=requirement.id, operation_id=operation_id)


class ReserveMaterialRequirementUseCase:
    def __init__(self, authorization: MeatProcessingAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()

    def execute(
        self, connection, *, requirement_id: str, operation_id: str, actor_user_id: str,
        quantity=0, weight=0, context: MeatProcessingExecutionContext | None = None,
    ) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.MATERIAL_ASSIGN)
        except MeatProcessingPermissionDeniedError as exc:
            return _fail(exc, operation_id)
        try:
            with MeatProcessingUnitOfWork(connection) as uow:
                requirement = uow.material_requirements.get(requirement_id)
                if requirement is None:
                    return MeatProcessingResult.fail(
                        "Requerimiento no encontrado", "REQUIREMENT_NOT_FOUND",
                        operation_id=operation_id)
                order = uow.orders.get(requirement.processing_order_id)
                denied = _scope_fail(context, order.branch_id, order.warehouse_id, operation_id)
                if denied is not None:
                    return denied
                requirement.reserve(quantity=quantity, weight=weight)
                uow.material_requirements.save(requirement)
                payload = build_meat_processing_event(
                    MeatProcessingEvents.PROCESSING_MATERIAL_RESERVED, operation_id=operation_id,
                    entity_id=requirement.id, branch_id=order.branch_id,
                    warehouse_id=order.warehouse_id, user_id=actor_user_id)
                uow.outbox.enqueue(
                    event_id=payload["event_id"],
                    event_name=MeatProcessingEvents.PROCESSING_MATERIAL_RESERVED,
                    payload_json=json.dumps(payload), operation_id=operation_id)
        except MeatProcessingError as exc:
            return _fail(exc, operation_id)
        return MeatProcessingResult.ok(
            "Requerimiento reservado", entity_id=requirement.id, operation_id=operation_id)


class AllocateMaterialRequirementUseCase:
    def __init__(self, authorization: MeatProcessingAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()

    def execute(
        self, connection, *, requirement_id: str, operation_id: str, actor_user_id: str,
        quantity=0, weight=0, context: MeatProcessingExecutionContext | None = None,
    ) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.MATERIAL_ASSIGN)
        except MeatProcessingPermissionDeniedError as exc:
            return _fail(exc, operation_id)
        try:
            with MeatProcessingUnitOfWork(connection) as uow:
                requirement = uow.material_requirements.get(requirement_id)
                if requirement is None:
                    return MeatProcessingResult.fail(
                        "Requerimiento no encontrado", "REQUIREMENT_NOT_FOUND",
                        operation_id=operation_id)
                order = uow.orders.get(requirement.processing_order_id)
                denied = _scope_fail(context, order.branch_id, order.warehouse_id, operation_id)
                if denied is not None:
                    return denied
                requirement.allocate(quantity=quantity, weight=weight)
                uow.material_requirements.save(requirement)
        except MeatProcessingError as exc:
            return _fail(exc, operation_id)
        return MeatProcessingResult.ok(
            "Requerimiento asignado", entity_id=requirement.id, operation_id=operation_id)


class AssignOperatorUseCase:
    def __init__(self, authorization: MeatProcessingAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()

    def execute(
        self, connection, *, order_id: str, operation_id: str, user_id: str,
        role_type: OperatorRole, actor_user_id: str, work_center_id: str | None = None,
        context: MeatProcessingExecutionContext | None = None,
    ) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.OPERATOR_ASSIGN)
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
                assignment = OperatorAssignment(
                    id=new_uuid(), operation_id=operation_id, processing_order_id=order_id,
                    user_id=user_id, role_type=role_type, work_center_id=work_center_id)
                uow.operator_assignments.save(assignment)
                uow.audit.record(
                    entity_type="OperatorAssignment", entity_id=assignment.id,
                    action="ASSIGNED", user_id=actor_user_id, operation_id=operation_id,
                    branch_id=order.branch_id, warehouse_id=order.warehouse_id,
                    processing_order_id=order_id)
        except MeatProcessingError as exc:
            return _fail(exc, operation_id)
        return MeatProcessingResult.ok(
            "Operario asignado", entity_id=assignment.id, operation_id=operation_id)


class ReleaseOperatorAssignmentUseCase:
    def __init__(self, authorization: MeatProcessingAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()

    def execute(
        self, connection, *, assignment_id: str, operation_id: str, actor_user_id: str,
    ) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.OPERATOR_RELEASE)
        except MeatProcessingPermissionDeniedError as exc:
            return _fail(exc, operation_id)
        try:
            with MeatProcessingUnitOfWork(connection) as uow:
                assignment = uow.operator_assignments.get(assignment_id)
                if assignment is None:
                    return MeatProcessingResult.fail(
                        "Asignación no encontrada", "ASSIGNMENT_NOT_FOUND",
                        operation_id=operation_id)
                if not assignment.is_active:
                    return MeatProcessingResult.ok(
                        "Asignación ya liberada (idempotente)", entity_id=assignment.id,
                        operation_id=operation_id, already_processed=True)
                assignment.release()
                uow.operator_assignments.save(assignment)
        except MeatProcessingError as exc:
            return _fail(exc, operation_id)
        return MeatProcessingResult.ok(
            "Operario liberado", entity_id=assignment.id, operation_id=operation_id)


class MarkProcessingOrderReadyUseCase:
    """§15: an order may not become READY while any requirement is still bare
    REQUIRED (not even reserved)."""

    def __init__(self, authorization: MeatProcessingAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()

    def execute(
        self, connection, *, order_id: str, operation_id: str, actor_user_id: str,
        context: MeatProcessingExecutionContext | None = None,
    ) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.MATERIAL_ASSIGN)
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
                if order.status is ProcessingOrderStatus.READY:
                    return MeatProcessingResult.ok(
                        "Orden ya lista (idempotente)", entity_id=order.id,
                        operation_id=operation_id, already_processed=True)
                requirements = uow.material_requirements.list_by_order(order_id)
                unsatisfied = [r.id for r in requirements if r.status in _UNSATISFIED]
                if unsatisfied:
                    return MeatProcessingResult.fail(
                        "Existen requerimientos sin reservar", "MATERIALS_NOT_READY",
                        operation_id=operation_id, requirement_ids=unsatisfied)
                order.mark_ready()
                uow.orders.save(order)
        except MeatProcessingError as exc:
            return _fail(exc, operation_id)
        return MeatProcessingResult.ok(
            "Orden lista para liberar", entity_id=order.id, operation_id=operation_id)
