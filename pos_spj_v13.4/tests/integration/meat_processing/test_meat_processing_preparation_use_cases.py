"""PROC-7 e2e: material requirements (reserve/allocate), operator assignment,
and the materials-ready gate."""

import importlib
import sqlite3
from decimal import Decimal

import pytest

from backend.application.meat_processing.use_cases import (
    AddMaterialRequirementUseCase,
    AllocateMaterialRequirementUseCase,
    AssignOperatorUseCase,
    CreateProcessingOrderUseCase,
    MarkProcessingOrderReadyUseCase,
    ReleaseOperatorAssignmentUseCase,
    ReserveMaterialRequirementUseCase,
)
from backend.domain.meat_processing.enums import OperatorRole, ProcessingOrderStatus, ProcessType
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
        "migrations.standalone.248_meat_processing_preparation_execution_schema").run(c)
    yield c
    c.close()


@pytest.fixture
def approved_order_id(conn):
    created = CreateProcessingOrderUseCase().execute(
        conn, operation_id=new_uuid(), branch_id=new_uuid(), warehouse_id=new_uuid(),
        process_type=ProcessType.CUTTING, target_product_id=new_uuid(),
        planned_quantity=Decimal("10"), planned_weight=Decimal("100"),
        actor_user_id=new_uuid())
    from backend.application.meat_processing.use_cases import ApproveProcessingOrderUseCase
    ApproveProcessingOrderUseCase().execute(
        conn, order_id=created.entity_id, operation_id=new_uuid(), actor_user_id=new_uuid())
    return created.entity_id


class TestMaterialRequirements:
    def test_add_requirement_moves_order_to_materials_pending(self, conn, approved_order_id):
        result = AddMaterialRequirementUseCase().execute(
            conn, order_id=approved_order_id, operation_id=new_uuid(), product_id=new_uuid(),
            required_quantity=Decimal("10"), required_weight=Decimal("100"),
            actor_user_id=new_uuid())
        assert result.success
        with MeatProcessingUnitOfWork(conn) as uow:
            order = uow.orders.get(approved_order_id)
            assert order.status is ProcessingOrderStatus.MATERIALS_PENDING

    def test_add_requirement_is_idempotent_on_operation_id(self, conn, approved_order_id):
        op_id = new_uuid()
        first = AddMaterialRequirementUseCase().execute(
            conn, order_id=approved_order_id, operation_id=op_id, product_id=new_uuid(),
            required_quantity=Decimal("1"), required_weight=Decimal("1"),
            actor_user_id=new_uuid())
        second = AddMaterialRequirementUseCase().execute(
            conn, order_id=approved_order_id, operation_id=op_id, product_id=new_uuid(),
            required_quantity=Decimal("1"), required_weight=Decimal("1"),
            actor_user_id=new_uuid())
        assert second.entity_id == first.entity_id
        assert second.data["already_processed"] is True

    def test_reserve_then_allocate(self, conn, approved_order_id):
        added = AddMaterialRequirementUseCase().execute(
            conn, order_id=approved_order_id, operation_id=new_uuid(), product_id=new_uuid(),
            required_quantity=Decimal("10"), required_weight=Decimal("100"),
            actor_user_id=new_uuid())
        reserved = ReserveMaterialRequirementUseCase().execute(
            conn, requirement_id=added.entity_id, operation_id=new_uuid(),
            actor_user_id=new_uuid(), quantity=Decimal("10"), weight=Decimal("100"))
        assert reserved.success
        allocated = AllocateMaterialRequirementUseCase().execute(
            conn, requirement_id=added.entity_id, operation_id=new_uuid(),
            actor_user_id=new_uuid(), quantity=Decimal("10"), weight=Decimal("100"))
        assert allocated.success
        with MeatProcessingUnitOfWork(conn) as uow:
            assert uow.material_requirements.get(added.entity_id).status.value == "ALLOCATED"

    def test_reserve_records_outbox_event(self, conn, approved_order_id):
        added = AddMaterialRequirementUseCase().execute(
            conn, order_id=approved_order_id, operation_id=new_uuid(), product_id=new_uuid(),
            required_quantity=Decimal("10"), required_weight=Decimal("100"),
            actor_user_id=new_uuid())
        op_id = new_uuid()
        ReserveMaterialRequirementUseCase().execute(
            conn, requirement_id=added.entity_id, operation_id=op_id, actor_user_id=new_uuid(),
            quantity=Decimal("5"), weight=Decimal("50"))
        with MeatProcessingUnitOfWork(conn) as uow:
            pending = uow.outbox.list_pending()
            assert any(row["operation_id"] == op_id for row in pending)


class TestOperatorAssignment:
    def test_assign_and_release(self, conn, approved_order_id):
        assigned = AssignOperatorUseCase().execute(
            conn, order_id=approved_order_id, operation_id=new_uuid(), user_id=new_uuid(),
            role_type=OperatorRole.CUTTER, actor_user_id=new_uuid())
        assert assigned.success
        with MeatProcessingUnitOfWork(conn) as uow:
            assert uow.operator_assignments.get(assigned.entity_id).is_active

        released = ReleaseOperatorAssignmentUseCase().execute(
            conn, assignment_id=assigned.entity_id, operation_id=new_uuid(),
            actor_user_id=new_uuid())
        assert released.success
        with MeatProcessingUnitOfWork(conn) as uow:
            assert not uow.operator_assignments.get(assigned.entity_id).is_active

    def test_release_is_idempotent(self, conn, approved_order_id):
        assigned = AssignOperatorUseCase().execute(
            conn, order_id=approved_order_id, operation_id=new_uuid(), user_id=new_uuid(),
            role_type=OperatorRole.WEIGHER, actor_user_id=new_uuid())
        ReleaseOperatorAssignmentUseCase().execute(
            conn, assignment_id=assigned.entity_id, operation_id=new_uuid(),
            actor_user_id=new_uuid())
        second = ReleaseOperatorAssignmentUseCase().execute(
            conn, assignment_id=assigned.entity_id, operation_id=new_uuid(),
            actor_user_id=new_uuid())
        assert second.data["already_processed"] is True


class TestMarkReady:
    def test_blocked_while_requirement_unsatisfied(self, conn, approved_order_id):
        AddMaterialRequirementUseCase().execute(
            conn, order_id=approved_order_id, operation_id=new_uuid(), product_id=new_uuid(),
            required_quantity=Decimal("10"), required_weight=Decimal("100"),
            actor_user_id=new_uuid())
        result = MarkProcessingOrderReadyUseCase().execute(
            conn, order_id=approved_order_id, operation_id=new_uuid(), actor_user_id=new_uuid())
        assert not result.success
        assert result.error_code == "MATERIALS_NOT_READY"

    def test_succeeds_once_reserved(self, conn, approved_order_id):
        added = AddMaterialRequirementUseCase().execute(
            conn, order_id=approved_order_id, operation_id=new_uuid(), product_id=new_uuid(),
            required_quantity=Decimal("10"), required_weight=Decimal("100"),
            actor_user_id=new_uuid())
        ReserveMaterialRequirementUseCase().execute(
            conn, requirement_id=added.entity_id, operation_id=new_uuid(),
            actor_user_id=new_uuid(), quantity=Decimal("10"), weight=Decimal("100"))
        result = MarkProcessingOrderReadyUseCase().execute(
            conn, order_id=approved_order_id, operation_id=new_uuid(), actor_user_id=new_uuid())
        assert result.success
        with MeatProcessingUnitOfWork(conn) as uow:
            assert uow.orders.get(approved_order_id).status is ProcessingOrderStatus.READY

    def test_with_zero_requirements_is_trivially_ready(self, conn, approved_order_id):
        result = MarkProcessingOrderReadyUseCase().execute(
            conn, order_id=approved_order_id, operation_id=new_uuid(), actor_user_id=new_uuid())
        assert result.success

    def test_is_idempotent(self, conn, approved_order_id):
        MarkProcessingOrderReadyUseCase().execute(
            conn, order_id=approved_order_id, operation_id=new_uuid(), actor_user_id=new_uuid())
        second = MarkProcessingOrderReadyUseCase().execute(
            conn, order_id=approved_order_id, operation_id=new_uuid(), actor_user_id=new_uuid())
        assert second.data["already_processed"] is True
