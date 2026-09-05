"""PROC-8 e2e: start → pause → resume → complete, steps, and incidents
(including an incident that pauses the order)."""

import importlib
import sqlite3
from decimal import Decimal

import pytest

from backend.application.meat_processing.use_cases import (
    ApproveProcessingOrderUseCase,
    CompleteProcessExecutionUseCase,
    CompleteProcessStepUseCase,
    CreateProcessingOrderUseCase,
    PauseProcessExecutionUseCase,
    ReleaseProcessingOrderUseCase,
    ReportProcessIncidentUseCase,
    ResolveProcessIncidentUseCase,
    ResumeProcessExecutionUseCase,
    StartProcessExecutionUseCase,
    StartProcessStepUseCase,
)
from backend.domain.meat_processing.enums import IncidentType, ProcessingOrderStatus, ProcessType
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
def released_order_id(conn):
    created = CreateProcessingOrderUseCase().execute(
        conn, operation_id=new_uuid(), branch_id=new_uuid(), warehouse_id=new_uuid(),
        process_type=ProcessType.CUTTING, target_product_id=new_uuid(),
        planned_quantity=Decimal("10"), planned_weight=Decimal("100"),
        actor_user_id=new_uuid())
    ApproveProcessingOrderUseCase().execute(
        conn, order_id=created.entity_id, operation_id=new_uuid(), actor_user_id=new_uuid())
    ReleaseProcessingOrderUseCase().execute(
        conn, order_id=created.entity_id, operation_id=new_uuid(), actor_user_id=new_uuid())
    return created.entity_id


class TestStartPauseResumeComplete:
    def test_start_moves_order_to_in_progress(self, conn, released_order_id):
        result = StartProcessExecutionUseCase().execute(
            conn, order_id=released_order_id, operation_id=new_uuid(), actor_user_id=new_uuid())
        assert result.success
        with MeatProcessingUnitOfWork(conn) as uow:
            assert uow.orders.get(released_order_id).status is ProcessingOrderStatus.IN_PROGRESS

    def test_start_is_idempotent(self, conn, released_order_id):
        StartProcessExecutionUseCase().execute(
            conn, order_id=released_order_id, operation_id=new_uuid(), actor_user_id=new_uuid())
        second = StartProcessExecutionUseCase().execute(
            conn, order_id=released_order_id, operation_id=new_uuid(), actor_user_id=new_uuid())
        assert second.data["already_processed"] is True

    def test_pause_then_resume_round_trip(self, conn, released_order_id):
        StartProcessExecutionUseCase().execute(
            conn, order_id=released_order_id, operation_id=new_uuid(), actor_user_id=new_uuid())
        paused = PauseProcessExecutionUseCase().execute(
            conn, order_id=released_order_id, operation_id=new_uuid(), actor_user_id=new_uuid())
        assert paused.success
        with MeatProcessingUnitOfWork(conn) as uow:
            assert uow.orders.get(released_order_id).status is ProcessingOrderStatus.PAUSED
        resumed = ResumeProcessExecutionUseCase().execute(
            conn, order_id=released_order_id, operation_id=new_uuid(), actor_user_id=new_uuid())
        assert resumed.success
        with MeatProcessingUnitOfWork(conn) as uow:
            assert uow.orders.get(released_order_id).status is ProcessingOrderStatus.IN_PROGRESS

    def test_pause_without_active_execution_fails(self, conn, released_order_id):
        result = PauseProcessExecutionUseCase().execute(
            conn, order_id=released_order_id, operation_id=new_uuid(), actor_user_id=new_uuid())
        assert not result.success
        assert result.error_code == "EXECUTION_NOT_FOUND"

    def test_complete_finishes_execution_and_order(self, conn, released_order_id):
        StartProcessExecutionUseCase().execute(
            conn, order_id=released_order_id, operation_id=new_uuid(), actor_user_id=new_uuid())
        result = CompleteProcessExecutionUseCase().execute(
            conn, order_id=released_order_id, operation_id=new_uuid(), actor_user_id=new_uuid())
        assert result.success
        with MeatProcessingUnitOfWork(conn) as uow:
            assert uow.orders.get(released_order_id).status is ProcessingOrderStatus.COMPLETED


class TestSteps:
    def _execution_id(self, conn, order_id):
        StartProcessExecutionUseCase().execute(
            conn, order_id=order_id, operation_id=new_uuid(), actor_user_id=new_uuid())
        with MeatProcessingUnitOfWork(conn) as uow:
            return uow.executions.list_by_order(order_id)[0].id

    def test_start_and_complete_step(self, conn, released_order_id):
        execution_id = self._execution_id(conn, released_order_id)
        started = StartProcessStepUseCase().execute(
            conn, process_execution_id=execution_id, operation_id=new_uuid(),
            step_name="deshuesado", actor_user_id=new_uuid())
        assert started.success
        completed = CompleteProcessStepUseCase().execute(
            conn, step_id=started.entity_id, operation_id=new_uuid(), actor_user_id=new_uuid())
        assert completed.success
        with MeatProcessingUnitOfWork(conn) as uow:
            step = uow.steps.get(started.entity_id)
            assert step.status.value == "COMPLETED"

    def test_complete_unknown_step_fails(self, conn):
        result = CompleteProcessStepUseCase().execute(
            conn, step_id=new_uuid(), operation_id=new_uuid(), actor_user_id=new_uuid())
        assert not result.success
        assert result.error_code == "STEP_NOT_FOUND"


class TestIncidents:
    def test_report_incident_without_pausing(self, conn, released_order_id):
        StartProcessExecutionUseCase().execute(
            conn, order_id=released_order_id, operation_id=new_uuid(), actor_user_id=new_uuid())
        result = ReportProcessIncidentUseCase().execute(
            conn, order_id=released_order_id, operation_id=new_uuid(),
            incident_type=IncidentType.EQUIPMENT_FAILURE, description="Báscula fuera de rango",
            actor_user_id=new_uuid())
        assert result.success
        with MeatProcessingUnitOfWork(conn) as uow:
            assert uow.orders.get(released_order_id).status is ProcessingOrderStatus.IN_PROGRESS

    def test_report_incident_with_pause_order_pauses_it(self, conn, released_order_id):
        StartProcessExecutionUseCase().execute(
            conn, order_id=released_order_id, operation_id=new_uuid(), actor_user_id=new_uuid())
        result = ReportProcessIncidentUseCase().execute(
            conn, order_id=released_order_id, operation_id=new_uuid(),
            incident_type=IncidentType.EQUIPMENT_FAILURE, description="Falla de báscula",
            actor_user_id=new_uuid(), pause_order=True)
        assert result.success
        with MeatProcessingUnitOfWork(conn) as uow:
            assert uow.orders.get(released_order_id).status is ProcessingOrderStatus.PAUSED

    def test_resolve_incident(self, conn, released_order_id):
        reported = ReportProcessIncidentUseCase().execute(
            conn, order_id=released_order_id, operation_id=new_uuid(),
            incident_type=IncidentType.MATERIAL_SHORTAGE, description="Falta materia prima",
            actor_user_id=new_uuid())
        resolved = ResolveProcessIncidentUseCase().execute(
            conn, incident_id=reported.entity_id, operation_id=new_uuid(),
            actor_user_id=new_uuid(), resolution_notes="Reabastecido")
        assert resolved.success
        second = ResolveProcessIncidentUseCase().execute(
            conn, incident_id=reported.entity_id, operation_id=new_uuid(),
            actor_user_id=new_uuid())
        assert second.data["already_processed"] is True
