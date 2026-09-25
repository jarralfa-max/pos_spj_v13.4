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
from tests.integration.meat_processing._quality_fake import record_decided_by_quality


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
        result = record_decided_by_quality(
            conn, output_id=output_id, operation_id=new_uuid(),
            decision=OutputQualityStatus.RELEASED, actor_user_id=new_uuid(),
        quality_inspection_id=new_uuid())
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
        result = record_decided_by_quality(
            conn, output_id=output_id, operation_id=new_uuid(),
            decision=OutputQualityStatus.CONDEMNED, actor_user_id=new_uuid(),
        quality_inspection_id=new_uuid())
        assert result.success
        assert result.data["blocked"] is True
        with MeatProcessingUnitOfWork(conn) as uow:
            pending = uow.outbox.list_pending()
            names = {row["event_name"] for row in pending}
            assert "PROCESSING_OUTPUT_BLOCKED" in names

    def test_is_idempotent_on_same_decision(self, conn, output_id):
        record_decided_by_quality(
            conn, output_id=output_id, operation_id=new_uuid(),
            decision=OutputQualityStatus.REJECTED, actor_user_id=new_uuid(),
        quality_inspection_id=new_uuid())
        second = record_decided_by_quality(
            conn, output_id=output_id, operation_id=new_uuid(),
            decision=OutputQualityStatus.REJECTED, actor_user_id=new_uuid(),
        quality_inspection_id=new_uuid())
        assert second.data["already_processed"] is True

    def test_unknown_output_fails(self, conn):
        result = record_decided_by_quality(
            conn, output_id=new_uuid(), operation_id=new_uuid(),
            decision=OutputQualityStatus.RELEASED, actor_user_id=new_uuid(),
        quality_inspection_id=new_uuid())
        assert not result.success
        assert result.error_code == "OUTPUT_NOT_FOUND"

    def test_who_captured_the_output_cannot_decide_its_quality(self, conn, output_id):
        with MeatProcessingUnitOfWork(conn) as uow:
            capturer = uow.outputs.get(output_id).captured_by_user_id
        result = record_decided_by_quality(
            conn, output_id=output_id, operation_id=new_uuid(),
            decision=OutputQualityStatus.RELEASED, actor_user_id=capturer,
            quality_inspection_id=new_uuid())
        assert not result.success
        assert result.error_code == "SEGREGATION_OF_DUTIES"
        with MeatProcessingUnitOfWork(conn) as uow:
            assert uow.outputs.get(output_id).quality_status is                 OutputQualityStatus.PENDING_INSPECTION

    def test_without_a_quality_inspection_there_is_no_decision(self, conn, output_id):
        result = record_decided_by_quality(
            conn, output_id=output_id, operation_id=new_uuid(),
            decision=OutputQualityStatus.RELEASED, actor_user_id=new_uuid(),
            quality_inspection_id="")
        assert not result.success
        assert result.error_code == "QUALITY_INSPECTION_REQUIRED"

    def test_only_quality_decisions_are_accepted(self, conn, output_id):
        result = record_decided_by_quality(
            conn, output_id=output_id, operation_id=new_uuid(),
            decision=OutputQualityStatus.NOT_REQUIRED, actor_user_id=new_uuid(),
            quality_inspection_id=new_uuid())
        assert not result.success
        assert result.error_code == "INVALID_QUALITY_DECISION"


class TestProcessingNeverDecidesQualityOnItsOwn:
    """Tener el permiso no basta: la decisión tiene que existir en Calidad."""

    def test_without_a_quality_decision_nothing_is_recorded(self, conn, output_id):
        result = RecordQualityDecisionUseCase().execute(
            conn, output_id=output_id, operation_id=new_uuid(),
            decision=OutputQualityStatus.RELEASED, actor_user_id=new_uuid(),
            quality_inspection_id=new_uuid())
        assert not result.success
        assert result.error_code == "QUALITY_DECISION_NOT_FOUND"
        with MeatProcessingUnitOfWork(conn) as uow:
            assert uow.outputs.get(output_id).quality_status is                 OutputQualityStatus.PENDING_INSPECTION

    @pytest.mark.parametrize("campo", ["decided_by_user_id", "subject_id", "status",
                                       "source_module"])
    def test_a_decision_that_does_not_match_quality_is_refused(self, conn, output_id, campo):
        from tests.integration.meat_processing._quality_fake import QualityDecided

        inspector = new_uuid()
        calidad = QualityDecided()
        inspeccion = calidad.decided(output_id=output_id,
                                     decision=OutputQualityStatus.RELEASED, actor=inspector)
        calidad.decision_of(inspeccion)[campo] = {
            "decided_by_user_id": new_uuid(), "subject_id": new_uuid(),
            "status": "BLOCKED", "source_module": "otro_modulo"}[campo]
        result = RecordQualityDecisionUseCase(quality_decisions=calidad).execute(
            conn, output_id=output_id, operation_id=new_uuid(),
            decision=OutputQualityStatus.RELEASED, actor_user_id=inspector,
            quality_inspection_id=inspeccion)
        assert not result.success
        assert result.error_code == "QUALITY_DECISION_NOT_FOUND"

