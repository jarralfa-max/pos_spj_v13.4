"""Resource and capacity use cases (PROC-19, §19/§33): the master-data
catalog área → centro de trabajo → estación → equipo, and equipment
assignment/maintenance lifecycle — the structural twin of
AssignOperatorUseCase/ReleaseOperatorAssignmentUseCase (PROC-7) but for
equipment rather than people.
"""

from __future__ import annotations

from backend.application.meat_processing.authorization import MeatProcessingAuthorizationPolicy
from backend.application.meat_processing.execution_context import (
    MeatProcessingExecutionContext,
)
from backend.application.meat_processing.permissions import MeatProcessingPermissions
from backend.application.meat_processing.result import MeatProcessingResult
from backend.application.meat_processing.use_cases._shared import fail as _fail
from backend.application.meat_processing.use_cases._shared import scope_fail as _scope_fail
from backend.domain.meat_processing.entities.equipment_assignment import EquipmentAssignment
from backend.domain.meat_processing.entities.production_area import ProductionArea
from backend.domain.meat_processing.entities.production_equipment import ProductionEquipment
from backend.domain.meat_processing.entities.production_station import ProductionStation
from backend.domain.meat_processing.entities.work_center import WorkCenter
from backend.domain.meat_processing.exceptions import (
    MeatProcessingError,
    MeatProcessingPermissionDeniedError,
)
from backend.infrastructure.db.repositories.meat_processing.unit_of_work import (
    MeatProcessingUnitOfWork,
)
from backend.shared.ids import new_uuid


class CreateProductionAreaUseCase:
    def __init__(self, authorization: MeatProcessingAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()

    def execute(
        self, connection, *, branch_id: str, warehouse_id: str, code: str, name: str,
        actor_user_id: str, context: MeatProcessingExecutionContext | None = None,
    ) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.RESOURCE_MANAGE)
        except MeatProcessingPermissionDeniedError as exc:
            return _fail(exc, None)
        denied = _scope_fail(context, branch_id, warehouse_id, None)
        if denied is not None:
            return denied
        try:
            with MeatProcessingUnitOfWork(connection) as uow:
                area = ProductionArea(
                    id=new_uuid(), branch_id=branch_id, warehouse_id=warehouse_id,
                    code=code, name=name)
                uow.production_areas.save(area)
        except MeatProcessingError as exc:
            return _fail(exc, None)
        return MeatProcessingResult.ok("Área de producción creada", entity_id=area.id)


class CreateWorkCenterUseCase:
    def __init__(self, authorization: MeatProcessingAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()

    def execute(
        self, connection, *, production_area_id: str, code: str, name: str, actor_user_id: str,
        capacity_per_hour=0, capacity_basis: str = "weight",
    ) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.RESOURCE_MANAGE)
        except MeatProcessingPermissionDeniedError as exc:
            return _fail(exc, None)
        try:
            with MeatProcessingUnitOfWork(connection) as uow:
                area = uow.production_areas.get(production_area_id)
                if area is None:
                    return MeatProcessingResult.fail(
                        "Área de producción no encontrada", "AREA_NOT_FOUND")
                work_center = WorkCenter(
                    id=new_uuid(), production_area_id=production_area_id, code=code,
                    name=name, capacity_per_hour=capacity_per_hour,
                    capacity_basis=capacity_basis)
                uow.work_centers.save(work_center)
        except MeatProcessingError as exc:
            return _fail(exc, None)
        return MeatProcessingResult.ok("Centro de trabajo creado", entity_id=work_center.id)


class CreateProductionStationUseCase:
    def __init__(self, authorization: MeatProcessingAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()

    def execute(
        self, connection, *, work_center_id: str, code: str, name: str, actor_user_id: str,
    ) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.RESOURCE_MANAGE)
        except MeatProcessingPermissionDeniedError as exc:
            return _fail(exc, None)
        try:
            with MeatProcessingUnitOfWork(connection) as uow:
                work_center = uow.work_centers.get(work_center_id)
                if work_center is None:
                    return MeatProcessingResult.fail(
                        "Centro de trabajo no encontrado", "WORK_CENTER_NOT_FOUND")
                station = ProductionStation(
                    id=new_uuid(), work_center_id=work_center_id, code=code, name=name)
                uow.production_stations.save(station)
        except MeatProcessingError as exc:
            return _fail(exc, None)
        return MeatProcessingResult.ok("Estación creada", entity_id=station.id)


class RegisterEquipmentUseCase:
    def __init__(self, authorization: MeatProcessingAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()

    def execute(
        self, connection, *, work_center_id: str, code: str, name: str, equipment_type: str,
        actor_user_id: str, station_id: str | None = None,
    ) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.EQUIPMENT_MANAGE)
        except MeatProcessingPermissionDeniedError as exc:
            return _fail(exc, None)
        try:
            with MeatProcessingUnitOfWork(connection) as uow:
                work_center = uow.work_centers.get(work_center_id)
                if work_center is None:
                    return MeatProcessingResult.fail(
                        "Centro de trabajo no encontrado", "WORK_CENTER_NOT_FOUND")
                equipment = ProductionEquipment(
                    id=new_uuid(), work_center_id=work_center_id, code=code, name=name,
                    equipment_type=equipment_type, station_id=station_id)
                uow.equipment.save(equipment)
                uow.audit.record(
                    entity_type="ProductionEquipment", entity_id=equipment.id,
                    action="REGISTERED", user_id=actor_user_id, operation_id=None,
                    branch_id=None, warehouse_id=None)
        except MeatProcessingError as exc:
            return _fail(exc, None)
        return MeatProcessingResult.ok("Equipo registrado", entity_id=equipment.id)


class StartEquipmentMaintenanceUseCase:
    def __init__(self, authorization: MeatProcessingAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()

    def execute(
        self, connection, *, equipment_id: str, actor_user_id: str,
    ) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.EQUIPMENT_MAINTENANCE)
        except MeatProcessingPermissionDeniedError as exc:
            return _fail(exc, None)
        try:
            with MeatProcessingUnitOfWork(connection) as uow:
                equipment = uow.equipment.get(equipment_id)
                if equipment is None:
                    return MeatProcessingResult.fail(
                        "Equipo no encontrado", "EQUIPMENT_NOT_FOUND")
                equipment.start_maintenance()
                uow.equipment.save(equipment)
                uow.audit.record(
                    entity_type="ProductionEquipment", entity_id=equipment.id,
                    action="MAINTENANCE_STARTED", user_id=actor_user_id, operation_id=None,
                    branch_id=None, warehouse_id=None)
        except MeatProcessingError as exc:
            return _fail(exc, None)
        return MeatProcessingResult.ok("Mantenimiento iniciado", entity_id=equipment.id)


class CompleteEquipmentMaintenanceUseCase:
    def __init__(self, authorization: MeatProcessingAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()

    def execute(
        self, connection, *, equipment_id: str, actor_user_id: str,
    ) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.EQUIPMENT_MAINTENANCE)
        except MeatProcessingPermissionDeniedError as exc:
            return _fail(exc, None)
        try:
            with MeatProcessingUnitOfWork(connection) as uow:
                equipment = uow.equipment.get(equipment_id)
                if equipment is None:
                    return MeatProcessingResult.fail(
                        "Equipo no encontrado", "EQUIPMENT_NOT_FOUND")
                equipment.complete_maintenance()
                uow.equipment.save(equipment)
                uow.audit.record(
                    entity_type="ProductionEquipment", entity_id=equipment.id,
                    action="MAINTENANCE_COMPLETED", user_id=actor_user_id, operation_id=None,
                    branch_id=None, warehouse_id=None)
        except MeatProcessingError as exc:
            return _fail(exc, None)
        return MeatProcessingResult.ok("Mantenimiento completado", entity_id=equipment.id)


class RetireEquipmentUseCase:
    def __init__(self, authorization: MeatProcessingAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()

    def execute(
        self, connection, *, equipment_id: str, actor_user_id: str,
    ) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.EQUIPMENT_MANAGE)
        except MeatProcessingPermissionDeniedError as exc:
            return _fail(exc, None)
        try:
            with MeatProcessingUnitOfWork(connection) as uow:
                equipment = uow.equipment.get(equipment_id)
                if equipment is None:
                    return MeatProcessingResult.fail(
                        "Equipo no encontrado", "EQUIPMENT_NOT_FOUND")
                equipment.retire()
                uow.equipment.save(equipment)
                uow.audit.record(
                    entity_type="ProductionEquipment", entity_id=equipment.id,
                    action="RETIRED", user_id=actor_user_id, operation_id=None,
                    branch_id=None, warehouse_id=None)
        except MeatProcessingError as exc:
            return _fail(exc, None)
        return MeatProcessingResult.ok("Equipo retirado", entity_id=equipment.id)


class AssignEquipmentUseCase:
    """Requires the equipment to be AVAILABLE — the one availability check
    PROC-19 makes without building a full scheduling engine (§19: "sin
    construir un APS completo", the same restraint PROC-5's
    CapacityValidationService already applied)."""

    def __init__(self, authorization: MeatProcessingAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()

    def execute(
        self, connection, *, order_id: str, equipment_id: str, operation_id: str,
        actor_user_id: str, context: MeatProcessingExecutionContext | None = None,
    ) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.EQUIPMENT_ASSIGN)
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
                equipment = uow.equipment.get(equipment_id)
                if equipment is None:
                    return MeatProcessingResult.fail(
                        "Equipo no encontrado", "EQUIPMENT_NOT_FOUND",
                        operation_id=operation_id)
                if not equipment.is_available:
                    return MeatProcessingResult.fail(
                        "El equipo no está disponible", "EQUIPMENT_NOT_AVAILABLE",
                        operation_id=operation_id)
                assignment = EquipmentAssignment(
                    id=new_uuid(), operation_id=operation_id, processing_order_id=order_id,
                    equipment_id=equipment_id)
                uow.equipment_assignments.save(assignment)
                uow.audit.record(
                    entity_type="EquipmentAssignment", entity_id=assignment.id,
                    action="ASSIGNED", user_id=actor_user_id, operation_id=operation_id,
                    branch_id=order.branch_id, warehouse_id=order.warehouse_id,
                    processing_order_id=order_id)
        except MeatProcessingError as exc:
            return _fail(exc, operation_id)
        return MeatProcessingResult.ok(
            "Equipo asignado", entity_id=assignment.id, operation_id=operation_id)


class ReleaseEquipmentAssignmentUseCase:
    def __init__(self, authorization: MeatProcessingAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()

    def execute(
        self, connection, *, assignment_id: str, operation_id: str, actor_user_id: str,
    ) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.EQUIPMENT_RELEASE)
        except MeatProcessingPermissionDeniedError as exc:
            return _fail(exc, operation_id)
        try:
            with MeatProcessingUnitOfWork(connection) as uow:
                assignment = uow.equipment_assignments.get(assignment_id)
                if assignment is None:
                    return MeatProcessingResult.fail(
                        "Asignación no encontrada", "ASSIGNMENT_NOT_FOUND",
                        operation_id=operation_id)
                if not assignment.is_active:
                    return MeatProcessingResult.ok(
                        "Asignación ya liberada (idempotente)", entity_id=assignment.id,
                        operation_id=operation_id, already_processed=True)
                assignment.release()
                uow.equipment_assignments.save(assignment)
        except MeatProcessingError as exc:
            return _fail(exc, operation_id)
        return MeatProcessingResult.ok(
            "Equipo liberado", entity_id=assignment.id, operation_id=operation_id)
