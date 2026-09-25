"""PROC-22 e2e: CloseProcessingOrderUseCase — the §35 capstone that checks
every cross-context precondition (consumption/output/weighing/quality/yield/
losses/inventory/costs) before closing, honestly failing on whichever is
still Null-ported."""

from decimal import Decimal

import pytest

from backend.application.meat_processing.use_cases import (
    ApproveYieldReconciliationUseCase,
    CaptureMaterialConsumptionUseCase,
    CaptureProcessOutputUseCase,
    CaptureProcessWeighingUseCase,
    CloseProcessingOrderUseCase,
    CompleteProcessExecutionUseCase,
    CreateProcessingOrderUseCase,
    PostMaterialConsumptionUseCase,
    PostProcessOutputUseCase,
    ReconcileYieldUseCase,
    StartProcessExecutionUseCase,
)
from backend.domain.meat_processing.enums import (
    OutputQualityStatus,
    OutputType,
    ProcessingOrderStatus,
    ProcessType,
    WeighingType,
)
from backend.infrastructure.db.repositories.meat_processing.unit_of_work import (
    MeatProcessingUnitOfWork,
)
from backend.shared.ids import new_uuid
from tests.integration.meat_processing._quality_fake import record_decided_by_quality
from tests.integration.meat_processing._generic_plant import build_db, released_order


@pytest.fixture
def conn():
    c = build_db()
    yield c
    c.close()


class _FakeInventoryPort:
    def post_consumption(self, **kwargs):
        return new_uuid()

    def post_output(self, **kwargs):
        return new_uuid()


class _FakeCostPort:
    def request_cost_allocation(self, **kwargs):
        return new_uuid()


def _completed_order(conn):
    """Drives a full order through the lifecycle up to COMPLETED, with every
    close precondition satisfiable EXCEPT costs_notified (left to the
    caller, so tests can choose whether to wire a cost port)."""
    approver, inspector = new_uuid(), new_uuid()
    planta, order_id, product_id = released_order(conn, peso="10")
    warehouse_id = planta.warehouse
    StartProcessExecutionUseCase().execute(
        conn, order_id=order_id, operation_id=new_uuid(), actor_user_id=approver)

    CaptureProcessWeighingUseCase().execute(
        conn, order_id=order_id, operation_id=new_uuid(), weighing_type=WeighingType.INPUT,
        gross_weight=Decimal("10"), actor_user_id=approver)

    consumption = CaptureMaterialConsumptionUseCase().execute(
        conn, order_id=order_id, operation_id=new_uuid(), product_id=product_id,
        warehouse_id=warehouse_id,
        planned_quantity=Decimal("10"), planned_weight=Decimal("10"),
        actual_quantity=Decimal("10"), actual_weight=Decimal("10"), actor_user_id=approver)
    PostMaterialConsumptionUseCase(inventory_port=_FakeInventoryPort()).execute(
        conn, consumption_id=consumption.entity_id, operation_id=new_uuid(),
        actor_user_id=approver)

    output = CaptureProcessOutputUseCase().execute(
        conn, order_id=order_id, operation_id=new_uuid(), product_id=new_uuid(),
        output_type=OutputType.MAIN_PRODUCT, quantity=Decimal("8"), weight=Decimal("8"),
        actor_user_id=approver)
    # La decisión llega de Calidad (otro usuario) con su inspección.
    assert record_decided_by_quality(
        conn, output_id=output.entity_id, operation_id=new_uuid(),
        decision=OutputQualityStatus.RELEASED, actor_user_id=inspector,
        quality_inspection_id=new_uuid()).success
    with MeatProcessingUnitOfWork(conn) as uow:
        salida = uow.outputs.get(output.entity_id)
        salida.place(lot_id=new_uuid(), location_id=planta.ubicacion)
        uow.outputs.save(salida)
    PostProcessOutputUseCase(inventory_port=_FakeInventoryPort()).execute(
        conn, output_id=output.entity_id, operation_id=new_uuid(), actor_user_id=approver)

    reconciled = ReconcileYieldUseCase().execute(
        conn, order_id=order_id, operation_id=new_uuid(), actor_user_id=approver,
        input_quantity=Decimal("10"), input_weight=Decimal("10"),
        expected_output_quantity=Decimal("8"), expected_output_weight=Decimal("8"),
        warning_pct=Decimal("5"), tolerance_pct=Decimal("10"), critical_pct=Decimal("20"))
    ApproveYieldReconciliationUseCase().execute(
        conn, reconciliation_id=reconciled.entity_id, operation_id=new_uuid(),
        actor_user_id=approver)

    CompleteProcessExecutionUseCase().execute(
        conn, order_id=order_id, operation_id=new_uuid(), actor_user_id=approver)
    with MeatProcessingUnitOfWork(conn) as uow:
        assert uow.orders.get(order_id).status is ProcessingOrderStatus.COMPLETED
    return order_id, approver


class TestCloseProcessingOrder:
    def test_fails_when_order_not_completed(self, conn):
        created = CreateProcessingOrderUseCase().execute(
            conn, operation_id=new_uuid(), branch_id=new_uuid(), warehouse_id=new_uuid(),
            process_type=ProcessType.CUTTING, target_product_id=new_uuid(),
            planned_quantity=Decimal("10"), planned_weight=Decimal("10"),
            actor_user_id=new_uuid())
        result = CloseProcessingOrderUseCase().execute(
            conn, order_id=created.entity_id, operation_id=new_uuid(), actor_user_id=new_uuid())
        assert not result.success
        assert result.error_code == "ORDER_NOT_COMPLETED"

    def test_fails_without_cost_allocation(self, conn):
        order_id, actor = _completed_order(conn)
        result = CloseProcessingOrderUseCase().execute(
            conn, order_id=order_id, operation_id=new_uuid(), actor_user_id=actor)
        assert not result.success
        assert result.error_code == "CLOSE_PRECONDITIONS_NOT_MET"
        assert "costs_notified" in result.data["pending_items"]

    def test_closes_when_every_precondition_is_met(self, conn):
        order_id, actor = _completed_order(conn)
        result = CloseProcessingOrderUseCase(cost_allocation_port=_FakeCostPort()).execute(
            conn, order_id=order_id, operation_id=new_uuid(), actor_user_id=actor)
        assert result.success, result.data
        with MeatProcessingUnitOfWork(conn) as uow:
            order = uow.orders.get(order_id)
            assert order.status is ProcessingOrderStatus.CLOSED
            pending = uow.outbox.list_pending()
            names = {row["event_name"] for row in pending}
            assert "PROCESSING_ORDER_CLOSED" in names

    def test_is_idempotent(self, conn):
        order_id, actor = _completed_order(conn)
        port = _FakeCostPort()
        CloseProcessingOrderUseCase(cost_allocation_port=port).execute(
            conn, order_id=order_id, operation_id=new_uuid(), actor_user_id=actor)
        second = CloseProcessingOrderUseCase(cost_allocation_port=port).execute(
            conn, order_id=order_id, operation_id=new_uuid(), actor_user_id=actor)
        assert second.data["already_processed"] is True

    def test_unknown_order_fails(self, conn):
        result = CloseProcessingOrderUseCase().execute(
            conn, order_id=new_uuid(), operation_id=new_uuid(), actor_user_id=new_uuid())
        assert not result.success
        assert result.error_code == "ORDER_NOT_FOUND"
