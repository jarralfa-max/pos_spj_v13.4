"""PROC-19 e2e: área → centro de trabajo → estación → equipo, y el ciclo de
asignación/liberación/mantenimiento de equipo sobre una orden real."""

import importlib
import sqlite3
from decimal import Decimal

import pytest

from backend.application.meat_processing.use_cases import (
    ApproveProcessingOrderUseCase,
    AssignEquipmentUseCase,
    CompleteEquipmentMaintenanceUseCase,
    CreateProcessingOrderUseCase,
    CreateProductionAreaUseCase,
    CreateProductionStationUseCase,
    CreateWorkCenterUseCase,
    RegisterEquipmentUseCase,
    ReleaseEquipmentAssignmentUseCase,
    RetireEquipmentUseCase,
    StartEquipmentMaintenanceUseCase,
)
from backend.domain.meat_processing.enums import EquipmentStatus, ProcessType
from backend.infrastructure.db.repositories.meat_processing.unit_of_work import (
    MeatProcessingUnitOfWork,
)
from backend.shared.ids import new_uuid


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    importlib.import_module(
        "migrations.standalone.187_meat_processing_bounded_context_schema").run(c)
    importlib.import_module(
        "migrations.standalone.252_meat_processing_resources_schema").run(c)
    yield c
    c.close()


@pytest.fixture
def area_id(conn):
    branch_id, warehouse_id = new_uuid(), new_uuid()
    result = CreateProductionAreaUseCase().execute(
        conn, branch_id=branch_id, warehouse_id=warehouse_id, code="DESP",
        name="Despiece", actor_user_id=new_uuid())
    assert result.success
    return result.entity_id


@pytest.fixture
def work_center_id(conn, area_id):
    result = CreateWorkCenterUseCase().execute(
        conn, production_area_id=area_id, code="WC1", name="Centro 1",
        actor_user_id=new_uuid(), capacity_per_hour=Decimal("100"), capacity_basis="weight")
    assert result.success
    return result.entity_id


@pytest.fixture
def equipment_id(conn, work_center_id):
    result = RegisterEquipmentUseCase().execute(
        conn, work_center_id=work_center_id, code="EQ1", name="Sierra",
        equipment_type="SAW", actor_user_id=new_uuid())
    assert result.success
    return result.entity_id


@pytest.fixture
def order_id(conn):
    created = CreateProcessingOrderUseCase().execute(
        conn, operation_id=new_uuid(), branch_id=new_uuid(), warehouse_id=new_uuid(),
        process_type=ProcessType.CUTTING, target_product_id=new_uuid(),
        planned_quantity=Decimal("10"), planned_weight=Decimal("10"),
        actor_user_id=new_uuid())
    ApproveProcessingOrderUseCase().execute(
        conn, order_id=created.entity_id, operation_id=new_uuid(), actor_user_id=new_uuid())
    return created.entity_id


class TestResourceCatalog:
    def test_creates_area_work_center_and_station(self, conn, work_center_id):
        result = CreateProductionStationUseCase().execute(
            conn, work_center_id=work_center_id, code="ST1", name="Estación 1",
            actor_user_id=new_uuid())
        assert result.success
        with MeatProcessingUnitOfWork(conn) as uow:
            work_center = uow.work_centers.get(work_center_id)
            assert work_center.capacity_per_hour == Decimal("100")
            stations = uow.production_stations.list_by_work_center(work_center_id)
            assert len(stations) == 1

    def test_work_center_unknown_area_fails(self, conn):
        result = CreateWorkCenterUseCase().execute(
            conn, production_area_id=new_uuid(), code="WC1", name="Centro 1",
            actor_user_id=new_uuid())
        assert not result.success
        assert result.error_code == "AREA_NOT_FOUND"

    def test_equipment_unknown_work_center_fails(self, conn):
        result = RegisterEquipmentUseCase().execute(
            conn, work_center_id=new_uuid(), code="EQ1", name="Sierra",
            equipment_type="SAW", actor_user_id=new_uuid())
        assert not result.success
        assert result.error_code == "WORK_CENTER_NOT_FOUND"


class TestEquipmentMaintenance:
    def test_maintenance_round_trip(self, conn, equipment_id):
        started = StartEquipmentMaintenanceUseCase().execute(
            conn, equipment_id=equipment_id, actor_user_id=new_uuid())
        assert started.success
        with MeatProcessingUnitOfWork(conn) as uow:
            assert uow.equipment.get(equipment_id).status is EquipmentStatus.MAINTENANCE
        completed = CompleteEquipmentMaintenanceUseCase().execute(
            conn, equipment_id=equipment_id, actor_user_id=new_uuid())
        assert completed.success
        with MeatProcessingUnitOfWork(conn) as uow:
            equipment = uow.equipment.get(equipment_id)
            assert equipment.status is EquipmentStatus.AVAILABLE
            assert equipment.last_maintenance_at is not None

    def test_retire_unknown_equipment_fails(self, conn):
        result = RetireEquipmentUseCase().execute(
            conn, equipment_id=new_uuid(), actor_user_id=new_uuid())
        assert not result.success
        assert result.error_code == "EQUIPMENT_NOT_FOUND"

    def test_retire_equipment(self, conn, equipment_id):
        result = RetireEquipmentUseCase().execute(
            conn, equipment_id=equipment_id, actor_user_id=new_uuid())
        assert result.success
        with MeatProcessingUnitOfWork(conn) as uow:
            assert uow.equipment.get(equipment_id).status is EquipmentStatus.RETIRED


class TestAssignEquipment:
    def test_assigns_available_equipment(self, conn, order_id, equipment_id):
        result = AssignEquipmentUseCase().execute(
            conn, order_id=order_id, equipment_id=equipment_id, operation_id=new_uuid(),
            actor_user_id=new_uuid())
        assert result.success
        with MeatProcessingUnitOfWork(conn) as uow:
            assignments = uow.equipment_assignments.list_by_order(order_id)
            assert len(assignments) == 1
            assert assignments[0].is_active

    def test_cannot_assign_equipment_in_maintenance(self, conn, order_id, equipment_id):
        StartEquipmentMaintenanceUseCase().execute(
            conn, equipment_id=equipment_id, actor_user_id=new_uuid())
        result = AssignEquipmentUseCase().execute(
            conn, order_id=order_id, equipment_id=equipment_id, operation_id=new_uuid(),
            actor_user_id=new_uuid())
        assert not result.success
        assert result.error_code == "EQUIPMENT_NOT_AVAILABLE"

    def test_unknown_order_fails(self, conn, equipment_id):
        result = AssignEquipmentUseCase().execute(
            conn, order_id=new_uuid(), equipment_id=equipment_id, operation_id=new_uuid(),
            actor_user_id=new_uuid())
        assert not result.success
        assert result.error_code == "ORDER_NOT_FOUND"

    def test_unknown_equipment_fails(self, conn, order_id):
        result = AssignEquipmentUseCase().execute(
            conn, order_id=order_id, equipment_id=new_uuid(), operation_id=new_uuid(),
            actor_user_id=new_uuid())
        assert not result.success
        assert result.error_code == "EQUIPMENT_NOT_FOUND"


class TestReleaseEquipmentAssignment:
    def test_releases(self, conn, order_id, equipment_id):
        assigned = AssignEquipmentUseCase().execute(
            conn, order_id=order_id, equipment_id=equipment_id, operation_id=new_uuid(),
            actor_user_id=new_uuid())
        result = ReleaseEquipmentAssignmentUseCase().execute(
            conn, assignment_id=assigned.entity_id, operation_id=new_uuid(),
            actor_user_id=new_uuid())
        assert result.success
        with MeatProcessingUnitOfWork(conn) as uow:
            assert not uow.equipment_assignments.get(assigned.entity_id).is_active

    def test_is_idempotent(self, conn, order_id, equipment_id):
        assigned = AssignEquipmentUseCase().execute(
            conn, order_id=order_id, equipment_id=equipment_id, operation_id=new_uuid(),
            actor_user_id=new_uuid())
        ReleaseEquipmentAssignmentUseCase().execute(
            conn, assignment_id=assigned.entity_id, operation_id=new_uuid(),
            actor_user_id=new_uuid())
        second = ReleaseEquipmentAssignmentUseCase().execute(
            conn, assignment_id=assigned.entity_id, operation_id=new_uuid(),
            actor_user_id=new_uuid())
        assert second.data["already_processed"] is True

    def test_unknown_assignment_fails(self, conn):
        result = ReleaseEquipmentAssignmentUseCase().execute(
            conn, assignment_id=new_uuid(), operation_id=new_uuid(), actor_user_id=new_uuid())
        assert not result.success
        assert result.error_code == "ASSIGNMENT_NOT_FOUND"
