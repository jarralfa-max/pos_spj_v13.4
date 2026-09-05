"""PROC-14/15 e2e: standalone yield reconciliation from previously captured
outputs, approval, and requesting a loss case for an out-of-tolerance yield."""

import importlib
import sqlite3
from decimal import Decimal

import pytest

from backend.application.meat_processing.use_cases import (
    ApproveProcessingOrderUseCase,
    ApproveYieldReconciliationUseCase,
    AssignOperatorUseCase,
    CaptureProcessOutputUseCase,
    CreateProcessingOrderUseCase,
    ReconcileYieldUseCase,
    RequestLossCaseForYieldVarianceUseCase,
)
from backend.domain.meat_processing.enums import OperatorRole, OutputType, ProcessType
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
        planned_quantity=Decimal("100"), planned_weight=Decimal("100"),
        actor_user_id=new_uuid())
    ApproveProcessingOrderUseCase().execute(
        conn, order_id=created.entity_id, operation_id=new_uuid(), actor_user_id=new_uuid())
    return created.entity_id


class TestReconcileYield:
    def test_reconciles_from_previously_captured_outputs(self, conn, approved_order_id):
        CaptureProcessOutputUseCase().execute(
            conn, order_id=approved_order_id, operation_id=new_uuid(), product_id=new_uuid(),
            output_type=OutputType.MAIN_PRODUCT, quantity=Decimal("69"), weight=Decimal("69"),
            actor_user_id=new_uuid())
        CaptureProcessOutputUseCase().execute(
            conn, order_id=approved_order_id, operation_id=new_uuid(), product_id=new_uuid(),
            output_type=OutputType.WASTE, quantity=Decimal("0"), weight=Decimal("2"),
            actor_user_id=new_uuid())

        result = ReconcileYieldUseCase().execute(
            conn, order_id=approved_order_id, operation_id=new_uuid(), actor_user_id=new_uuid(),
            input_quantity=Decimal("100"), input_weight=Decimal("100"),
            expected_output_quantity=Decimal("70"), expected_output_weight=Decimal("70"),
            warning_pct=Decimal("2"), tolerance_pct=Decimal("5"), critical_pct=Decimal("10"))
        assert result.success
        assert result.data["yield_status"] == "WITHIN_TOLERANCE"

    def test_fails_when_no_outputs_captured_yet(self, conn, approved_order_id):
        result = ReconcileYieldUseCase().execute(
            conn, order_id=approved_order_id, operation_id=new_uuid(), actor_user_id=new_uuid(),
            input_quantity=Decimal("100"), input_weight=Decimal("100"),
            expected_output_quantity=Decimal("70"), expected_output_weight=Decimal("70"),
            warning_pct=Decimal("2"), tolerance_pct=Decimal("5"), critical_pct=Decimal("10"))
        assert not result.success
        assert result.error_code == "NO_OUTPUTS"


class TestApproveYieldReconciliation:
    def _reconciliation_id(self, conn, order_id, main_weight=Decimal("68")):
        CaptureProcessOutputUseCase().execute(
            conn, order_id=order_id, operation_id=new_uuid(), product_id=new_uuid(),
            output_type=OutputType.MAIN_PRODUCT, quantity=main_weight, weight=main_weight,
            actor_user_id=new_uuid())
        result = ReconcileYieldUseCase().execute(
            conn, order_id=order_id, operation_id=new_uuid(), actor_user_id=new_uuid(),
            input_quantity=Decimal("100"), input_weight=Decimal("100"),
            expected_output_quantity=Decimal("70"), expected_output_weight=Decimal("70"),
            warning_pct=Decimal("2"), tolerance_pct=Decimal("5"), critical_pct=Decimal("10"))
        return result.entity_id

    def test_approve_happy_path_and_idempotency(self, conn, approved_order_id):
        reconciliation_id = self._reconciliation_id(conn, approved_order_id)
        first = ApproveYieldReconciliationUseCase().execute(
            conn, reconciliation_id=reconciliation_id, operation_id=new_uuid(),
            actor_user_id=new_uuid())
        assert first.success
        with MeatProcessingUnitOfWork(conn) as uow:
            assert uow.yield_reconciliations.get(reconciliation_id).status.value == "APPROVED"
        second = ApproveYieldReconciliationUseCase().execute(
            conn, reconciliation_id=reconciliation_id, operation_id=new_uuid(),
            actor_user_id=new_uuid())
        assert second.data["already_processed"] is True

    def test_approve_unknown_reconciliation_fails(self, conn):
        result = ApproveYieldReconciliationUseCase().execute(
            conn, reconciliation_id=new_uuid(), operation_id=new_uuid(),
            actor_user_id=new_uuid())
        assert not result.success
        assert result.error_code == "RECONCILIATION_NOT_FOUND"


class TestRequestLossCaseForYieldVariance:
    def _critical_reconciliation_id(self, conn, order_id):
        CaptureProcessOutputUseCase().execute(
            conn, order_id=order_id, operation_id=new_uuid(), product_id=new_uuid(),
            output_type=OutputType.MAIN_PRODUCT, quantity=Decimal("40"), weight=Decimal("40"),
            actor_user_id=new_uuid())
        result = ReconcileYieldUseCase().execute(
            conn, order_id=order_id, operation_id=new_uuid(), actor_user_id=new_uuid(),
            input_quantity=Decimal("100"), input_weight=Decimal("100"),
            expected_output_quantity=Decimal("90"), expected_output_weight=Decimal("90"),
            warning_pct=Decimal("2"), tolerance_pct=Decimal("5"), critical_pct=Decimal("10"))
        assert result.data["yield_status"] == "CRITICAL"
        return result.entity_id

    def test_rejects_within_tolerance_reconciliation(self, conn, approved_order_id):
        CaptureProcessOutputUseCase().execute(
            conn, order_id=approved_order_id, operation_id=new_uuid(), product_id=new_uuid(),
            output_type=OutputType.MAIN_PRODUCT, quantity=Decimal("70"), weight=Decimal("70"),
            actor_user_id=new_uuid())
        result = ReconcileYieldUseCase().execute(
            conn, order_id=approved_order_id, operation_id=new_uuid(), actor_user_id=new_uuid(),
            input_quantity=Decimal("100"), input_weight=Decimal("100"),
            expected_output_quantity=Decimal("70"), expected_output_weight=Decimal("70"),
            warning_pct=Decimal("2"), tolerance_pct=Decimal("5"), critical_pct=Decimal("10"))
        loss_result = RequestLossCaseForYieldVarianceUseCase().execute(
            conn, reconciliation_id=result.entity_id, operation_id=new_uuid(),
            actor_user_id=new_uuid())
        assert not loss_result.success
        assert loss_result.error_code == "WITHIN_TOLERANCE"

    def test_without_port_reports_pending_integration(self, conn, approved_order_id):
        reconciliation_id = self._critical_reconciliation_id(conn, approved_order_id)
        result = RequestLossCaseForYieldVarianceUseCase().execute(
            conn, reconciliation_id=reconciliation_id, operation_id=new_uuid(),
            actor_user_id=new_uuid())
        assert not result.success
        assert result.error_code == "LOSSES_INTEGRATION_PENDING"

    def test_with_fake_port_succeeds_carries_operator_ids_and_is_idempotent(
            self, conn, approved_order_id):
        operator_id = new_uuid()
        AssignOperatorUseCase().execute(
            conn, order_id=approved_order_id, operation_id=new_uuid(), user_id=operator_id,
            role_type=OperatorRole.CUTTER, actor_user_id=new_uuid())
        reconciliation_id = self._critical_reconciliation_id(conn, approved_order_id)

        captured = {}

        class FakeLossPort:
            def request_loss_case(self, **kwargs):
                captured.update(kwargs)
                return new_uuid()

        use_case = RequestLossCaseForYieldVarianceUseCase(loss_case_port=FakeLossPort())
        op_id = new_uuid()
        first = use_case.execute(
            conn, reconciliation_id=reconciliation_id, operation_id=op_id,
            actor_user_id=new_uuid())
        assert first.success
        assert operator_id in captured["operator_ids"]

        second = use_case.execute(
            conn, reconciliation_id=reconciliation_id, operation_id=op_id,
            actor_user_id=new_uuid())
        assert second.data["already_processed"] is True

    def test_request_unknown_reconciliation_fails(self, conn):
        result = RequestLossCaseForYieldVarianceUseCase().execute(
            conn, reconciliation_id=new_uuid(), operation_id=new_uuid(),
            actor_user_id=new_uuid())
        assert not result.success
        assert result.error_code == "RECONCILIATION_NOT_FOUND"
