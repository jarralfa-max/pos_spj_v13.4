"""PROC-16 e2e: requesting inspection and recording Calidad's decision —
Procesamiento never classifies, only asks and records."""

import importlib
import sqlite3
from decimal import Decimal

import pytest

from backend.application.meat_processing.use_cases import (
    ApproveProcessingOrderUseCase,
    CaptureProcessOutputUseCase,
    CreateProcessingOrderUseCase,
    RecordQualityDecisionUseCase,
    RequestQualityInspectionUseCase,
)
from backend.domain.meat_processing.enums import OutputQualityStatus, OutputType, ProcessType
from backend.infrastructure.db.repositories.meat_processing.unit_of_work import (
    MeatProcessingUnitOfWork,
)
from backend.shared.ids import new_uuid


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    importlib.import_module(
        "migrations.standalone.187_meat_processing_bounded_context_schema").run(c)
    yield c
    c.close()


@pytest.fixture
def output_id(conn):
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
    return captured.entity_id


class TestRequestQualityInspection:
    def test_without_port_reports_pending_integration(self, conn, output_id):
        result = RequestQualityInspectionUseCase().execute(
            conn, output_id=output_id, operation_id=new_uuid(), actor_user_id=new_uuid())
        assert not result.success
        assert result.error_code == "QUALITY_INTEGRATION_PENDING"

    def test_with_fake_port_succeeds_and_is_audited(self, conn, output_id):
        class FakePort:
            def request_inspection(self, **kwargs):
                return new_uuid()

        result = RequestQualityInspectionUseCase(quality_port=FakePort()).execute(
            conn, output_id=output_id, operation_id=new_uuid(), actor_user_id=new_uuid())
        assert result.success
        assert result.data["inspection_request_id"]
        with MeatProcessingUnitOfWork(conn) as uow:
            entries = uow.audit.list_for_entity("ProcessOutput", output_id)
            assert any(e["action"] == "QUALITY_INSPECTION_REQUESTED" for e in entries)

    def test_unknown_output_fails(self, conn):
        result = RequestQualityInspectionUseCase().execute(
            conn, output_id=new_uuid(), operation_id=new_uuid(), actor_user_id=new_uuid())
        assert not result.success
        assert result.error_code == "OUTPUT_NOT_FOUND"


class TestRecordQualityDecision:
    def test_release_emits_released_event(self, conn, output_id):
        result = RecordQualityDecisionUseCase().execute(
            conn, output_id=output_id, operation_id=new_uuid(),
            decision=OutputQualityStatus.RELEASED, actor_user_id=new_uuid())
        assert result.success
        assert result.data["blocked"] is False
        with MeatProcessingUnitOfWork(conn) as uow:
            output = uow.outputs.get(output_id)
            assert output.quality_status is OutputQualityStatus.RELEASED
            assert output.is_releasable_to_stock
            pending = uow.outbox.list_pending()
            names = {row["event_name"] for row in pending}
            assert "PROCESSING_OUTPUT_RELEASED" in names

    def test_condemn_emits_blocked_event(self, conn, output_id):
        result = RecordQualityDecisionUseCase().execute(
            conn, output_id=output_id, operation_id=new_uuid(),
            decision=OutputQualityStatus.CONDEMNED, actor_user_id=new_uuid())
        assert result.success
        assert result.data["blocked"] is True
        with MeatProcessingUnitOfWork(conn) as uow:
            pending = uow.outbox.list_pending()
            names = {row["event_name"] for row in pending}
            assert "PROCESSING_OUTPUT_BLOCKED" in names

    def test_is_idempotent_on_same_decision(self, conn, output_id):
        RecordQualityDecisionUseCase().execute(
            conn, output_id=output_id, operation_id=new_uuid(),
            decision=OutputQualityStatus.REJECTED, actor_user_id=new_uuid())
        second = RecordQualityDecisionUseCase().execute(
            conn, output_id=output_id, operation_id=new_uuid(),
            decision=OutputQualityStatus.REJECTED, actor_user_id=new_uuid())
        assert second.data["already_processed"] is True

    def test_unknown_output_fails(self, conn):
        result = RecordQualityDecisionUseCase().execute(
            conn, output_id=new_uuid(), operation_id=new_uuid(),
            decision=OutputQualityStatus.RELEASED, actor_user_id=new_uuid())
        assert not result.success
        assert result.error_code == "OUTPUT_NOT_FOUND"
