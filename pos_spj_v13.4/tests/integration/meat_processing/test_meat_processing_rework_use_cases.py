"""PROC-17 e2e: producto bloqueado → crear reproceso → aprobar → ejecutar
(nueva ProcessingOrder, sin tocar la original) → completar → cerrar."""

import importlib
import sqlite3
from decimal import Decimal

import pytest

from backend.application.meat_processing.use_cases import (
    ApproveProcessingOrderUseCase,
    ApproveReworkOrderUseCase,
    CaptureProcessOutputUseCase,
    CloseReworkOrderUseCase,
    CompleteReworkOrderUseCase,
    CreateProcessingOrderUseCase,
    CreateReworkOrderUseCase,
    RecordQualityDecisionUseCase,
    StartReworkExecutionUseCase,
)
from backend.domain.meat_processing.enums import (
    OutputQualityStatus,
    OutputType,
    ProcessType,
    ReworkOrderStatus,
    ReworkOrigin,
)
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
        "migrations.standalone.250_meat_processing_rework_schema").run(c)
    yield c
    c.close()


@pytest.fixture
def blocked_output_id(conn):
    created = CreateProcessingOrderUseCase().execute(
        conn, operation_id=new_uuid(), branch_id=new_uuid(), warehouse_id=new_uuid(),
        process_type=ProcessType.CUTTING, target_product_id=new_uuid(),
        planned_quantity=Decimal("10"), planned_weight=Decimal("10"),
        actor_user_id=new_uuid())
    ApproveProcessingOrderUseCase().execute(
        conn, order_id=created.entity_id, operation_id=new_uuid(), actor_user_id=new_uuid())
    captured = CaptureProcessOutputUseCase().execute(
        conn, order_id=created.entity_id, operation_id=new_uuid(), product_id=new_uuid(),
        output_type=OutputType.MAIN_PRODUCT, quantity=Decimal("5"), weight=Decimal("5"),
        actor_user_id=new_uuid())
    RecordQualityDecisionUseCase().execute(
        conn, output_id=captured.entity_id, operation_id=new_uuid(),
        decision=OutputQualityStatus.REWORK_REQUIRED, actor_user_id=new_uuid())
    return captured.entity_id


class TestCreateReworkOrder:
    def test_creates_from_blocked_output(self, conn, blocked_output_id):
        result = CreateReworkOrderUseCase().execute(
            conn, source_output_id=blocked_output_id, operation_id=new_uuid(),
            origin=ReworkOrigin.QUALITY_DECISION, actor_user_id=new_uuid())
        assert result.success
        with MeatProcessingUnitOfWork(conn) as uow:
            rework = uow.rework_orders.get(result.entity_id)
            assert rework.status is ReworkOrderStatus.CREATED

    def test_fails_when_output_not_blocked(self, conn):
        created = CreateProcessingOrderUseCase().execute(
            conn, operation_id=new_uuid(), branch_id=new_uuid(), warehouse_id=new_uuid(),
            process_type=ProcessType.CUTTING, target_product_id=new_uuid(),
            planned_quantity=Decimal("10"), planned_weight=Decimal("10"),
            actor_user_id=new_uuid())
        ApproveProcessingOrderUseCase().execute(
            conn, order_id=created.entity_id, operation_id=new_uuid(), actor_user_id=new_uuid())
        captured = CaptureProcessOutputUseCase().execute(
            conn, order_id=created.entity_id, operation_id=new_uuid(), product_id=new_uuid(),
            output_type=OutputType.MAIN_PRODUCT, quantity=Decimal("5"), weight=Decimal("5"),
            actor_user_id=new_uuid())
        result = CreateReworkOrderUseCase().execute(
            conn, source_output_id=captured.entity_id, operation_id=new_uuid(),
            origin=ReworkOrigin.QUALITY_DECISION, actor_user_id=new_uuid())
        assert not result.success
        assert result.error_code == "OUTPUT_NOT_BLOCKED"

    def test_unknown_output_fails(self, conn):
        result = CreateReworkOrderUseCase().execute(
            conn, source_output_id=new_uuid(), operation_id=new_uuid(),
            origin=ReworkOrigin.QUALITY_DECISION, actor_user_id=new_uuid())
        assert not result.success
        assert result.error_code == "OUTPUT_NOT_FOUND"


@pytest.fixture
def rework_id(conn, blocked_output_id):
    created = CreateReworkOrderUseCase().execute(
        conn, source_output_id=blocked_output_id, operation_id=new_uuid(),
        origin=ReworkOrigin.QUALITY_DECISION, actor_user_id=new_uuid())
    return created.entity_id


class TestApproveReworkOrder:
    def test_approves(self, conn, rework_id):
        result = ApproveReworkOrderUseCase().execute(
            conn, rework_order_id=rework_id, operation_id=new_uuid(), actor_user_id=new_uuid())
        assert result.success
        with MeatProcessingUnitOfWork(conn) as uow:
            assert uow.rework_orders.get(rework_id).status is ReworkOrderStatus.APPROVED

    def test_is_idempotent(self, conn, rework_id):
        approver = new_uuid()
        ApproveReworkOrderUseCase().execute(
            conn, rework_order_id=rework_id, operation_id=new_uuid(), actor_user_id=approver)
        second = ApproveReworkOrderUseCase().execute(
            conn, rework_order_id=rework_id, operation_id=new_uuid(), actor_user_id=approver)
        assert second.data["already_processed"] is True

    def test_unknown_rework_fails(self, conn):
        result = ApproveReworkOrderUseCase().execute(
            conn, rework_order_id=new_uuid(), operation_id=new_uuid(), actor_user_id=new_uuid())
        assert not result.success
        assert result.error_code == "REWORK_NOT_FOUND"


@pytest.fixture
def approved_rework_id(conn, rework_id):
    ApproveReworkOrderUseCase().execute(
        conn, rework_order_id=rework_id, operation_id=new_uuid(), actor_user_id=new_uuid())
    return rework_id


class TestStartReworkExecution:
    def test_creates_new_processing_order_without_touching_source(
            self, conn, approved_rework_id, blocked_output_id):
        with MeatProcessingUnitOfWork(conn) as uow:
            source_output = uow.outputs.get(blocked_output_id)
            source_order_id = source_output.processing_order_id

        result = StartReworkExecutionUseCase().execute(
            conn, rework_order_id=approved_rework_id, operation_id=new_uuid(),
            branch_id=new_uuid(), warehouse_id=new_uuid(), process_type=ProcessType.TRIMMING,
            actor_user_id=new_uuid())
        assert result.success
        new_order_id = result.data["processing_order_id"]
        assert new_order_id != source_order_id
        with MeatProcessingUnitOfWork(conn) as uow:
            new_order = uow.orders.get(new_order_id)
            assert new_order.source_type == "REWORK_ORDER"
            assert new_order.source_reference_id == approved_rework_id
            rework = uow.rework_orders.get(approved_rework_id)
            assert rework.status is ReworkOrderStatus.IN_PROGRESS
            assert rework.processing_order_id == new_order_id

    def test_is_idempotent(self, conn, approved_rework_id):
        kwargs = dict(
            rework_order_id=approved_rework_id, branch_id=new_uuid(),
            warehouse_id=new_uuid(), process_type=ProcessType.TRIMMING, actor_user_id=new_uuid())
        first = StartReworkExecutionUseCase().execute(conn, operation_id=new_uuid(), **kwargs)
        second = StartReworkExecutionUseCase().execute(conn, operation_id=new_uuid(), **kwargs)
        assert second.data["already_processed"] is True
        assert second.data["processing_order_id"] == first.data["processing_order_id"]

    def test_unknown_rework_fails(self, conn):
        result = StartReworkExecutionUseCase().execute(
            conn, rework_order_id=new_uuid(), operation_id=new_uuid(), branch_id=new_uuid(),
            warehouse_id=new_uuid(), process_type=ProcessType.TRIMMING, actor_user_id=new_uuid())
        assert not result.success
        assert result.error_code == "REWORK_NOT_FOUND"


@pytest.fixture
def in_progress_rework_id(conn, approved_rework_id):
    StartReworkExecutionUseCase().execute(
        conn, rework_order_id=approved_rework_id, operation_id=new_uuid(), branch_id=new_uuid(),
        warehouse_id=new_uuid(), process_type=ProcessType.TRIMMING, actor_user_id=new_uuid())
    return approved_rework_id


class TestCompleteReworkOrder:
    def test_completes_and_emits_event(self, conn, in_progress_rework_id):
        result = CompleteReworkOrderUseCase().execute(
            conn, rework_order_id=in_progress_rework_id, operation_id=new_uuid(),
            actor_user_id=new_uuid())
        assert result.success
        with MeatProcessingUnitOfWork(conn) as uow:
            assert uow.rework_orders.get(
                in_progress_rework_id).status is ReworkOrderStatus.COMPLETED
            pending = uow.outbox.list_pending()
            names = {row["event_name"] for row in pending}
            assert "PROCESSING_REWORK_COMPLETED" in names

    def test_is_idempotent(self, conn, in_progress_rework_id):
        CompleteReworkOrderUseCase().execute(
            conn, rework_order_id=in_progress_rework_id, operation_id=new_uuid(),
            actor_user_id=new_uuid())
        second = CompleteReworkOrderUseCase().execute(
            conn, rework_order_id=in_progress_rework_id, operation_id=new_uuid(),
            actor_user_id=new_uuid())
        assert second.data["already_processed"] is True

    def test_unknown_rework_fails(self, conn):
        result = CompleteReworkOrderUseCase().execute(
            conn, rework_order_id=new_uuid(), operation_id=new_uuid(), actor_user_id=new_uuid())
        assert not result.success
        assert result.error_code == "REWORK_NOT_FOUND"


class TestCloseReworkOrder:
    def test_closes(self, conn, in_progress_rework_id):
        CompleteReworkOrderUseCase().execute(
            conn, rework_order_id=in_progress_rework_id, operation_id=new_uuid(),
            actor_user_id=new_uuid())
        result = CloseReworkOrderUseCase().execute(
            conn, rework_order_id=in_progress_rework_id, operation_id=new_uuid(),
            actor_user_id=new_uuid())
        assert result.success
        with MeatProcessingUnitOfWork(conn) as uow:
            assert uow.rework_orders.get(
                in_progress_rework_id).status is ReworkOrderStatus.CLOSED

    def test_is_idempotent(self, conn, in_progress_rework_id):
        CompleteReworkOrderUseCase().execute(
            conn, rework_order_id=in_progress_rework_id, operation_id=new_uuid(),
            actor_user_id=new_uuid())
        CloseReworkOrderUseCase().execute(
            conn, rework_order_id=in_progress_rework_id, operation_id=new_uuid(),
            actor_user_id=new_uuid())
        second = CloseReworkOrderUseCase().execute(
            conn, rework_order_id=in_progress_rework_id, operation_id=new_uuid(),
            actor_user_id=new_uuid())
        assert second.data["already_processed"] is True

    def test_unknown_rework_fails(self, conn):
        result = CloseReworkOrderUseCase().execute(
            conn, rework_order_id=new_uuid(), operation_id=new_uuid(), actor_user_id=new_uuid())
        assert not result.success
        assert result.error_code == "REWORK_NOT_FOUND"
