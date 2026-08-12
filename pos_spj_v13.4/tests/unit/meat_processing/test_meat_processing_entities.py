from decimal import Decimal

import pytest

from backend.domain.meat_processing.entities import (
    MaterialConsumption,
    ProcessExecution,
    ProcessOutput,
    ProcessWeighing,
    ProcessingBatch,
    ProcessingOrder,
    YieldReconciliation,
)
from backend.domain.meat_processing.enums import (
    ConsumptionStatus,
    ExecutionStatus,
    OutputQualityStatus,
    OutputType,
    ProcessingBatchStatus,
    ProcessingOrderStatus,
    ProcessType,
    WeighingType,
    YieldStatus,
)
from backend.domain.meat_processing.exceptions import (
    MeatProcessingInvariantError,
    MeatProcessingStateTransitionError,
)
from backend.shared.ids import new_uuid


# -- ProcessingOrder --------------------------------------------------------------

def _order(**overrides) -> ProcessingOrder:
    base = dict(
        id=new_uuid(), operation_id=new_uuid(), branch_id=new_uuid(),
        warehouse_id=new_uuid(), process_type=ProcessType.CUTTING,
        target_product_id=new_uuid(), created_by_user_id=new_uuid(),
        planned_quantity=Decimal("10"), planned_weight=Decimal("100"),
    )
    base.update(overrides)
    return ProcessingOrder(**base)


def test_processing_order_rejects_float_quantity():
    with pytest.raises(TypeError):
        _order(planned_quantity=10.0)


def test_processing_order_rejects_equal_id_and_operation_id():
    same = new_uuid()
    with pytest.raises(MeatProcessingInvariantError):
        _order(id=same, operation_id=same)


def test_processing_order_requires_positive_quantity_or_weight():
    with pytest.raises(MeatProcessingInvariantError):
        _order(planned_quantity=Decimal("0"), planned_weight=Decimal("0"))


def test_processing_order_full_lifecycle_happy_path():
    creator = new_uuid()
    order = _order(created_by_user_id=creator)
    assert order.status is ProcessingOrderStatus.DRAFT

    order.submit_for_approval()
    assert order.status is ProcessingOrderStatus.PENDING_APPROVAL

    order.approve(actor_user_id=new_uuid())
    assert order.status is ProcessingOrderStatus.APPROVED

    order.mark_materials_pending()
    assert order.status is ProcessingOrderStatus.MATERIALS_PENDING
    order.mark_ready()
    assert order.status is ProcessingOrderStatus.READY

    order.release(actor_user_id=new_uuid())
    assert order.status is ProcessingOrderStatus.RELEASED

    order.start(actor_user_id=new_uuid())
    assert order.status is ProcessingOrderStatus.IN_PROGRESS

    order.pause()
    assert order.status is ProcessingOrderStatus.PAUSED
    order.resume()
    assert order.status is ProcessingOrderStatus.IN_PROGRESS

    closer = new_uuid()
    order.complete(actor_user_id=new_uuid())
    assert order.status is ProcessingOrderStatus.COMPLETED
    order.close(actor_user_id=closer)
    assert order.status is ProcessingOrderStatus.CLOSED

    order.reverse(actor_user_id=new_uuid())
    assert order.status is ProcessingOrderStatus.REVERSED


def test_processing_order_creator_cannot_approve_own_order():
    creator = new_uuid()
    order = _order(created_by_user_id=creator)
    order.submit_for_approval()
    with pytest.raises(MeatProcessingInvariantError):
        order.approve(actor_user_id=creator)


def test_processing_order_closer_cannot_reverse_own_closure():
    order = _order()
    order.submit_for_approval()
    order.approve(actor_user_id=new_uuid())
    order.release(actor_user_id=new_uuid())
    order.start(actor_user_id=new_uuid())
    order.complete(actor_user_id=new_uuid())
    closer = new_uuid()
    order.close(actor_user_id=closer)
    with pytest.raises(MeatProcessingInvariantError):
        order.reverse(actor_user_id=closer)


def test_processing_order_rejects_illegal_transition():
    order = _order()
    with pytest.raises(MeatProcessingStateTransitionError):
        order.start(actor_user_id=new_uuid())


def test_processing_order_cancel_only_from_pre_release_states():
    order = _order()
    order.submit_for_approval()
    order.approve(actor_user_id=new_uuid())
    order.release(actor_user_id=new_uuid())
    order.start(actor_user_id=new_uuid())
    with pytest.raises(MeatProcessingStateTransitionError):
        order.cancel()


def test_processing_order_close_is_terminal_and_immutable_to_reopen():
    order = _order()
    order.submit_for_approval()
    order.approve(actor_user_id=new_uuid())
    order.release(actor_user_id=new_uuid())
    order.start(actor_user_id=new_uuid())
    order.complete(actor_user_id=new_uuid())
    order.close(actor_user_id=new_uuid())
    with pytest.raises(MeatProcessingStateTransitionError):
        order.close(actor_user_id=new_uuid())
    with pytest.raises(MeatProcessingStateTransitionError):
        order.start(actor_user_id=new_uuid())


# -- ProcessingBatch --------------------------------------------------------------

def _batch(**overrides) -> ProcessingBatch:
    base = dict(id=new_uuid(), operation_id=new_uuid(), processing_order_id=new_uuid(),
                batch_number="LPR-2026-000001")
    base.update(overrides)
    return ProcessingBatch(**base)


def test_processing_batch_lifecycle():
    batch = _batch()
    assert batch.status is ProcessingBatchStatus.PLANNED
    batch.start()
    assert batch.status is ProcessingBatchStatus.IN_PROGRESS
    batch.record_actuals(actual_quantity=Decimal("9.5"), actual_weight=Decimal("95"))
    batch.complete()
    assert batch.status is ProcessingBatchStatus.COMPLETED
    batch.assign_inventory_lot(inventory_lot_id=new_uuid())


def test_processing_batch_rejects_negative_actuals():
    batch = _batch()
    batch.start()
    with pytest.raises(MeatProcessingInvariantError):
        batch.record_actuals(actual_quantity=Decimal("-1"), actual_weight=Decimal("0"))


def test_processing_batch_requires_batch_number():
    with pytest.raises(MeatProcessingInvariantError):
        _batch(batch_number="  ")


def test_processing_batch_cancel_from_in_progress():
    batch = _batch()
    batch.start()
    batch.cancel()
    assert batch.status is ProcessingBatchStatus.CANCELLED
    with pytest.raises(MeatProcessingStateTransitionError):
        batch.complete()


# -- ProcessExecution ---------------------------------------------------------------

def _execution(**overrides) -> ProcessExecution:
    base = dict(id=new_uuid(), operation_id=new_uuid(), processing_order_id=new_uuid())
    base.update(overrides)
    return ProcessExecution(**base)


def test_process_execution_lifecycle():
    execution = _execution()
    assert execution.status is ExecutionStatus.NOT_STARTED
    execution.start()
    assert execution.status is ExecutionStatus.ACTIVE
    execution.pause()
    assert execution.status is ExecutionStatus.PAUSED
    execution.resume()
    assert execution.status is ExecutionStatus.ACTIVE
    execution.complete()
    assert execution.status is ExecutionStatus.COMPLETED
    assert execution.duration_seconds is not None


def test_process_execution_fail_only_from_active_or_paused():
    execution = _execution()
    with pytest.raises(MeatProcessingStateTransitionError):
        execution.fail()
    execution.start()
    execution.fail()
    assert execution.status is ExecutionStatus.FAILED


# -- MaterialConsumption ------------------------------------------------------------

def _consumption(**overrides) -> MaterialConsumption:
    base = dict(id=new_uuid(), operation_id=new_uuid(), processing_order_id=new_uuid(),
                product_id=new_uuid(), warehouse_id=new_uuid(), captured_by_user_id=new_uuid(),
                planned_quantity=Decimal("10"), planned_weight=Decimal("100"))
    base.update(overrides)
    return MaterialConsumption(**base)


def test_material_consumption_lifecycle():
    consumption = _consumption()
    assert consumption.status is ConsumptionStatus.DRAFT
    consumption.record_actuals(actual_quantity=Decimal("9"), actual_weight=Decimal("90"))
    assert consumption.status is ConsumptionStatus.PENDING_POSTING
    consumption.post(inventory_operation_id=new_uuid())
    assert consumption.status is ConsumptionStatus.POSTED
    consumption.reverse()
    assert consumption.status is ConsumptionStatus.REVERSED


def test_material_consumption_cannot_post_before_recording_actuals():
    consumption = _consumption()
    with pytest.raises(MeatProcessingStateTransitionError):
        consumption.post(inventory_operation_id=new_uuid())


def test_material_consumption_requires_unit():
    with pytest.raises(MeatProcessingInvariantError):
        _consumption(unit="  ")


# -- ProcessOutput --------------------------------------------------------------------

def _output(**overrides) -> ProcessOutput:
    base = dict(id=new_uuid(), operation_id=new_uuid(), processing_order_id=new_uuid(),
                product_id=new_uuid(), warehouse_id=new_uuid(), captured_by_user_id=new_uuid(),
                output_type=OutputType.MAIN_PRODUCT, quantity=Decimal("5"), weight=Decimal("50"))
    base.update(overrides)
    return ProcessOutput(**base)


def test_process_output_defaults_to_pending_inspection_and_not_releasable():
    output = _output()
    assert output.quality_status is OutputQualityStatus.PENDING_INSPECTION
    assert output.is_releasable_to_stock is False


def test_process_output_mark_quality_status_and_release():
    output = _output()
    output.mark_quality_status(OutputQualityStatus.RELEASED)
    assert output.is_releasable_to_stock is True


def test_process_output_requires_quantity_or_weight():
    with pytest.raises(MeatProcessingInvariantError):
        _output(quantity=Decimal("0"), weight=Decimal("0"))


def test_process_output_rejects_negative_pieces():
    with pytest.raises(MeatProcessingInvariantError):
        _output(pieces=-1)


# -- ProcessWeighing -----------------------------------------------------------------

def _weighing(**overrides) -> ProcessWeighing:
    base = dict(id=new_uuid(), operation_id=new_uuid(), processing_order_id=new_uuid(),
                captured_by_user_id=new_uuid(), weighing_type=WeighingType.INPUT,
                gross_weight=Decimal("100"), tare_weight=Decimal("5"))
    base.update(overrides)
    return ProcessWeighing(**base)


def test_process_weighing_net_weight_computed():
    weighing = _weighing()
    assert weighing.net_weight == Decimal("95")


def test_process_weighing_tare_cannot_exceed_gross():
    with pytest.raises(MeatProcessingInvariantError):
        _weighing(gross_weight=Decimal("10"), tare_weight=Decimal("20"))


def test_process_weighing_unstable_requires_manual_override():
    with pytest.raises(MeatProcessingInvariantError):
        _weighing(stable=False, manual_override=False)


def test_process_weighing_manual_override_requires_authorization():
    with pytest.raises(MeatProcessingInvariantError):
        _weighing(manual_override=True, authorized_by_user_id=None)
    weighing = _weighing(stable=False, manual_override=True,
                          authorized_by_user_id=new_uuid())
    assert weighing.manual_override is True


# -- YieldReconciliation --------------------------------------------------------------

def _reconciliation(**overrides) -> YieldReconciliation:
    base = dict(
        id=new_uuid(), operation_id=new_uuid(), processing_order_id=new_uuid(),
        input_quantity=Decimal("10"), input_weight=Decimal("100"),
        expected_output_quantity=Decimal("9"), expected_output_weight=Decimal("90"),
        actual_output_quantity=Decimal("8.8"), actual_output_weight=Decimal("88"),
        tolerance_pct=Decimal("5"),
    )
    base.update(overrides)
    return YieldReconciliation(**base)


def test_yield_reconciliation_variance_and_unexplained_difference():
    reconciliation = _reconciliation(waste_weight=Decimal("10"))
    assert reconciliation.variance_pct is not None
    # (88 - 90) / 90 * 100
    assert reconciliation.variance_pct == (Decimal("-2") / Decimal("90")) * Decimal("100")
    # 100 - (88 + 0 + 0 + 10) = 2
    assert reconciliation.unexplained_difference == Decimal("2")


def test_yield_reconciliation_classification_and_approval_flow():
    reconciliation = _reconciliation()
    assert reconciliation.status is YieldStatus.PENDING_REVIEW
    reconciliation.apply_classification(YieldStatus.WARNING)
    assert reconciliation.status is YieldStatus.WARNING
    reconciliation.approve(actor_user_id=new_uuid())
    assert reconciliation.status is YieldStatus.APPROVED


def test_yield_reconciliation_cannot_approve_before_classification():
    reconciliation = _reconciliation()
    with pytest.raises(MeatProcessingStateTransitionError):
        reconciliation.approve(actor_user_id=new_uuid())


def test_yield_reconciliation_rejects_negative_fields():
    with pytest.raises(MeatProcessingInvariantError):
        _reconciliation(waste_weight=Decimal("-1"))
