"""PROC-10/11/12 e2e: single output capture, inventory receipt posting, the
despiece/derivados composite (multi-output + yield reconciliation), and
chaining an output into a downstream order's consumption (BOM multinivel)."""

import importlib
import sqlite3
from decimal import Decimal

import pytest

from backend.application.meat_processing.use_cases import (
    ApproveProcessingOrderUseCase,
    CaptureProcessOutputUseCase,
    ChainOutputAsConsumptionUseCase,
    CreateProcessingOrderUseCase,
    PostProcessOutputUseCase,
    RecordProcessOutputsUseCase,
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
    importlib.import_module(
        "migrations.standalone.248_meat_processing_preparation_execution_schema").run(c)
    importlib.import_module(
        "migrations.standalone.251_meat_processing_genealogy_schema").run(c)
    yield c
    c.close()


@pytest.fixture
def approved_order_id(conn):
    created = CreateProcessingOrderUseCase().execute(
        conn, operation_id=new_uuid(), branch_id=new_uuid(), warehouse_id=new_uuid(),
        process_type=ProcessType.CUTTING, target_product_id=new_uuid(),
        planned_quantity=Decimal("100"), planned_weight=Decimal("100"),
        actor_user_id=new_uuid())
    ApproveProcessingOrderUseCase().execute(
        conn, order_id=created.entity_id, operation_id=new_uuid(), actor_user_id=new_uuid())
    return created.entity_id


class TestCaptureProcessOutput:
    def test_capture_main_product(self, conn, approved_order_id):
        result = CaptureProcessOutputUseCase().execute(
            conn, order_id=approved_order_id, operation_id=new_uuid(), product_id=new_uuid(),
            output_type=OutputType.MAIN_PRODUCT, quantity=Decimal("50"),
            weight=Decimal("50"), actor_user_id=new_uuid())
        assert result.success
        with MeatProcessingUnitOfWork(conn) as uow:
            output = uow.outputs.get(result.entity_id)
            assert output.quality_status is OutputQualityStatus.PENDING_INSPECTION

    def test_capture_co_product(self, conn, approved_order_id):
        result = CaptureProcessOutputUseCase().execute(
            conn, order_id=approved_order_id, operation_id=new_uuid(), product_id=new_uuid(),
            output_type=OutputType.CO_PRODUCT, quantity=Decimal("10"),
            weight=Decimal("10"), actor_user_id=new_uuid())
        assert result.success

    def test_capture_unknown_order_fails(self, conn):
        result = CaptureProcessOutputUseCase().execute(
            conn, order_id=new_uuid(), operation_id=new_uuid(), product_id=new_uuid(),
            output_type=OutputType.WASTE, quantity=Decimal("1"), weight=Decimal("1"),
            actor_user_id=new_uuid())
        assert not result.success
        assert result.error_code == "ORDER_NOT_FOUND"


class TestPostProcessOutput:
    def _output_id(self, conn, order_id, output_type=OutputType.MAIN_PRODUCT):
        return CaptureProcessOutputUseCase().execute(
            conn, order_id=order_id, operation_id=new_uuid(), product_id=new_uuid(),
            output_type=output_type, quantity=Decimal("10"), weight=Decimal("10"),
            actor_user_id=new_uuid()).entity_id

    def test_post_without_port_reports_pending_integration(self, conn, approved_order_id):
        output_id = self._output_id(conn, approved_order_id)
        result = PostProcessOutputUseCase().execute(
            conn, output_id=output_id, operation_id=new_uuid(), actor_user_id=new_uuid())
        assert not result.success
        assert result.error_code == "INVENTORY_INTEGRATION_PENDING"

    def test_post_with_fake_port_succeeds_and_is_idempotent(self, conn, approved_order_id):
        output_id = self._output_id(conn, approved_order_id)

        class FakePort:
            def post_output(self, **kwargs):
                return new_uuid()

        use_case = PostProcessOutputUseCase(inventory_port=FakePort())
        first = use_case.execute(
            conn, output_id=output_id, operation_id=new_uuid(), actor_user_id=new_uuid())
        assert first.success
        second = use_case.execute(
            conn, output_id=output_id, operation_id=new_uuid(), actor_user_id=new_uuid())
        assert second.data["already_processed"] is True

    def test_post_blocked_by_quality_is_rejected(self, conn, approved_order_id):
        output_id = self._output_id(conn, approved_order_id)
        with MeatProcessingUnitOfWork(conn) as uow:
            output = uow.outputs.get(output_id)
            output.mark_quality_status(OutputQualityStatus.CONDEMNED)
            uow.outputs.save(output)
        result = PostProcessOutputUseCase().execute(
            conn, output_id=output_id, operation_id=new_uuid(), actor_user_id=new_uuid())
        assert not result.success
        assert result.error_code == "OUTPUT_QUALITY_BLOCKED"


class TestRecordProcessOutputs:
    def _lines(self):
        return [
            {"product_id": new_uuid(), "output_type": OutputType.MAIN_PRODUCT,
             "quantity": Decimal("70"), "weight": Decimal("70")},
            {"product_id": new_uuid(), "output_type": OutputType.CO_PRODUCT,
             "weight": Decimal("15")},
            {"product_id": new_uuid(), "output_type": OutputType.BY_PRODUCT,
             "weight": Decimal("8")},
            {"product_id": new_uuid(), "output_type": OutputType.WASTE,
             "weight": Decimal("5")},
        ]

    def test_within_tolerance_records_all_outputs_and_yield(self, conn, approved_order_id):
        result = RecordProcessOutputsUseCase().execute(
            conn, order_id=approved_order_id, operation_id=new_uuid(), actor_user_id=new_uuid(),
            input_quantity=Decimal("100"), input_weight=Decimal("100"),
            expected_output_quantity=Decimal("70"), expected_output_weight=Decimal("70"),
            outputs=self._lines(),
            warning_pct=Decimal("2"), tolerance_pct=Decimal("5"), critical_pct=Decimal("10"))
        assert result.success
        assert len(result.data["output_ids"]) == 4
        assert result.data["yield_status"] == "WITHIN_TOLERANCE"
        with MeatProcessingUnitOfWork(conn) as uow:
            outputs = uow.outputs.list_by_order(approved_order_id)
            assert len(outputs) == 4
            reconciliations = uow.yield_reconciliations.list_by_order(approved_order_id)
            assert len(reconciliations) == 1

    def test_is_idempotent_on_outer_operation_id(self, conn, approved_order_id):
        op_id = new_uuid()
        first = RecordProcessOutputsUseCase().execute(
            conn, order_id=approved_order_id, operation_id=op_id, actor_user_id=new_uuid(),
            input_quantity=Decimal("100"), input_weight=Decimal("100"),
            expected_output_quantity=Decimal("70"), expected_output_weight=Decimal("70"),
            outputs=self._lines(),
            warning_pct=Decimal("2"), tolerance_pct=Decimal("5"), critical_pct=Decimal("10"))
        second = RecordProcessOutputsUseCase().execute(
            conn, order_id=approved_order_id, operation_id=op_id, actor_user_id=new_uuid(),
            input_quantity=Decimal("100"), input_weight=Decimal("100"),
            expected_output_quantity=Decimal("70"), expected_output_weight=Decimal("70"),
            outputs=self._lines(),
            warning_pct=Decimal("2"), tolerance_pct=Decimal("5"), critical_pct=Decimal("10"))
        assert second.data["already_processed"] is True
        with MeatProcessingUnitOfWork(conn) as uow:
            # second call must not have captured a duplicate set of outputs
            assert len(uow.outputs.list_by_order(approved_order_id)) == 4

    def test_out_of_tolerance_emits_alert_event(self, conn, approved_order_id):
        lines = [
            {"product_id": new_uuid(), "output_type": OutputType.MAIN_PRODUCT,
             "quantity": Decimal("50"), "weight": Decimal("50")},
        ]
        result = RecordProcessOutputsUseCase().execute(
            conn, order_id=approved_order_id, operation_id=new_uuid(), actor_user_id=new_uuid(),
            input_quantity=Decimal("100"), input_weight=Decimal("100"),
            expected_output_quantity=Decimal("90"), expected_output_weight=Decimal("90"),
            outputs=lines,
            warning_pct=Decimal("2"), tolerance_pct=Decimal("5"), critical_pct=Decimal("10"))
        assert result.success
        assert result.data["yield_status"] == "CRITICAL"
        with MeatProcessingUnitOfWork(conn) as uow:
            pending = uow.outbox.list_pending()
            event_names = {row["event_name"] for row in pending}
            assert "PROCESSING_YIELD_OUT_OF_TOLERANCE" in event_names

    def test_requires_at_least_one_output(self, conn, approved_order_id):
        result = RecordProcessOutputsUseCase().execute(
            conn, order_id=approved_order_id, operation_id=new_uuid(), actor_user_id=new_uuid(),
            input_quantity=Decimal("100"), input_weight=Decimal("100"),
            expected_output_quantity=Decimal("70"), expected_output_weight=Decimal("70"),
            outputs=[],
            warning_pct=Decimal("2"), tolerance_pct=Decimal("5"), critical_pct=Decimal("10"))
        assert not result.success
        assert result.error_code == "NO_OUTPUTS"


class TestChainOutputAsConsumption:
    def test_chains_upstream_output_into_downstream_consumption(self, conn, approved_order_id):
        upstream = CaptureProcessOutputUseCase().execute(
            conn, order_id=approved_order_id, operation_id=new_uuid(), product_id=new_uuid(),
            output_type=OutputType.SEMI_FINISHED, quantity=Decimal("20"),
            weight=Decimal("20"), actor_user_id=new_uuid())

        downstream_created = CreateProcessingOrderUseCase().execute(
            conn, operation_id=new_uuid(), branch_id=new_uuid(), warehouse_id=new_uuid(),
            process_type=ProcessType.MIXING, target_product_id=new_uuid(),
            planned_quantity=Decimal("20"), planned_weight=Decimal("20"),
            actor_user_id=new_uuid())

        result = ChainOutputAsConsumptionUseCase().execute(
            conn, upstream_output_id=upstream.entity_id,
            downstream_order_id=downstream_created.entity_id, operation_id=new_uuid(),
            actor_user_id=new_uuid())
        assert result.success
        with MeatProcessingUnitOfWork(conn) as uow:
            consumption = uow.consumptions.get(result.entity_id)
            assert consumption.processing_order_id == downstream_created.entity_id
            assert consumption.actual_quantity == Decimal("20")
            assert consumption.status.value == "PENDING_POSTING"

    def test_blocked_upstream_output_cannot_chain(self, conn, approved_order_id):
        upstream = CaptureProcessOutputUseCase().execute(
            conn, order_id=approved_order_id, operation_id=new_uuid(), product_id=new_uuid(),
            output_type=OutputType.SEMI_FINISHED, quantity=Decimal("5"), weight=Decimal("5"),
            actor_user_id=new_uuid())
        with MeatProcessingUnitOfWork(conn) as uow:
            output = uow.outputs.get(upstream.entity_id)
            output.mark_quality_status(OutputQualityStatus.REJECTED)
            uow.outputs.save(output)

        downstream_created = CreateProcessingOrderUseCase().execute(
            conn, operation_id=new_uuid(), branch_id=new_uuid(), warehouse_id=new_uuid(),
            process_type=ProcessType.MIXING, target_product_id=new_uuid(),
            planned_quantity=Decimal("5"), planned_weight=Decimal("5"),
            actor_user_id=new_uuid())

        result = ChainOutputAsConsumptionUseCase().execute(
            conn, upstream_output_id=upstream.entity_id,
            downstream_order_id=downstream_created.entity_id, operation_id=new_uuid(),
            actor_user_id=new_uuid())
        assert not result.success
        assert result.error_code == "OUTPUT_QUALITY_BLOCKED"
