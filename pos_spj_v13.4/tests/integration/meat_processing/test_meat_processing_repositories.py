import importlib
import sqlite3
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
    OutputType,
    ProcessType,
    WeighingType,
)
from backend.infrastructure.db.repositories.meat_processing.unit_of_work import (
    MeatProcessingUnitOfWork,
)
from backend.shared.ids import new_uuid


@pytest.fixture
def uow():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    importlib.import_module(
        "migrations.standalone.187_meat_processing_bounded_context_schema"
    ).run(conn)
    return MeatProcessingUnitOfWork(conn)


def _order(**overrides) -> ProcessingOrder:
    base = dict(
        id=new_uuid(), operation_id=new_uuid(), branch_id=new_uuid(),
        warehouse_id=new_uuid(), process_type=ProcessType.CUTTING,
        target_product_id=new_uuid(), created_by_user_id=new_uuid(),
        planned_quantity=Decimal("10"), planned_weight=Decimal("100"),
    )
    base.update(overrides)
    return ProcessingOrder(**base)


def test_processing_order_round_trips(uow):
    order = _order(recipe_version_id=new_uuid(), priority=5)
    order.submit_for_approval()
    order.approve(actor_user_id=new_uuid())
    with uow:
        uow.orders.save(order)
    loaded = uow.orders.get(order.id)
    assert loaded == order
    assert uow.orders.get_by_operation_id(order.operation_id) == order
    assert order in uow.orders.list_by_branch(order.branch_id)


def test_processing_order_upsert_persists_status_transition(uow):
    order = _order()
    with uow:
        uow.orders.save(order)
    order.submit_for_approval()
    order.approve(actor_user_id=new_uuid())
    with uow:
        uow.orders.save(order)
    assert uow.orders.get(order.id).status == order.status


def test_processing_batch_round_trips_with_source_lots(uow):
    order = _order()
    with uow:
        uow.orders.save(order)
    batch = ProcessingBatch(
        id=new_uuid(), operation_id=new_uuid(), processing_order_id=order.id,
        batch_number="LPR-2026-000001", source_lot_ids=(new_uuid(), new_uuid()),
        planned_quantity=Decimal("10"), planned_weight=Decimal("100"))
    batch.start()
    with uow:
        uow.batches.save(batch)
    loaded = uow.batches.get(batch.id)
    assert loaded == batch
    assert set(loaded.source_lot_ids) == set(batch.source_lot_ids)
    assert batch in uow.batches.list_by_order(order.id)


def test_process_execution_round_trips(uow):
    order = _order()
    with uow:
        uow.orders.save(order)
    execution = ProcessExecution(
        id=new_uuid(), operation_id=new_uuid(), processing_order_id=order.id)
    execution.start()
    execution.pause()
    execution.resume()
    with uow:
        uow.executions.save(execution)
    loaded = uow.executions.get(execution.id)
    assert loaded == execution
    assert execution in uow.executions.list_by_order(order.id)


def test_material_consumption_round_trips(uow):
    order = _order()
    with uow:
        uow.orders.save(order)
    consumption = MaterialConsumption(
        id=new_uuid(), operation_id=new_uuid(), processing_order_id=order.id,
        product_id=new_uuid(), warehouse_id=new_uuid(), captured_by_user_id=new_uuid(),
        planned_quantity=Decimal("10"), planned_weight=Decimal("100"))
    consumption.record_actuals(actual_quantity=Decimal("9"), actual_weight=Decimal("90"))
    consumption.post(inventory_operation_id=new_uuid())
    with uow:
        uow.consumptions.save(consumption)
    loaded = uow.consumptions.get(consumption.id)
    assert loaded == consumption
    assert consumption in uow.consumptions.list_by_order(order.id)


def test_process_output_round_trips(uow):
    order = _order()
    with uow:
        uow.orders.save(order)
    output = ProcessOutput(
        id=new_uuid(), operation_id=new_uuid(), processing_order_id=order.id,
        product_id=new_uuid(), warehouse_id=new_uuid(), captured_by_user_id=new_uuid(),
        output_type=OutputType.CO_PRODUCT, quantity=Decimal("2"), weight=Decimal("20"),
        pieces=4)
    with uow:
        uow.outputs.save(output)
    loaded = uow.outputs.get(output.id)
    assert loaded == output
    assert output in uow.outputs.list_by_order(order.id)


def test_process_weighing_round_trips(uow):
    order = _order()
    with uow:
        uow.orders.save(order)
    weighing = ProcessWeighing(
        id=new_uuid(), operation_id=new_uuid(), processing_order_id=order.id,
        captured_by_user_id=new_uuid(), weighing_type=WeighingType.INPUT,
        gross_weight=Decimal("100"), tare_weight=Decimal("5"))
    with uow:
        uow.weighings.save(weighing)
    loaded = uow.weighings.get(weighing.id)
    assert loaded == weighing
    assert weighing in uow.weighings.list_by_order(order.id)


def test_yield_reconciliation_round_trips(uow):
    order = _order()
    with uow:
        uow.orders.save(order)
    reconciliation = YieldReconciliation(
        id=new_uuid(), operation_id=new_uuid(), processing_order_id=order.id,
        input_quantity=Decimal("10"), input_weight=Decimal("100"),
        expected_output_quantity=Decimal("9"), expected_output_weight=Decimal("90"),
        actual_output_quantity=Decimal("8.8"), actual_output_weight=Decimal("88"),
        tolerance_pct=Decimal("5"))
    with uow:
        uow.yield_reconciliations.save(reconciliation)
    loaded = uow.yield_reconciliations.get(reconciliation.id)
    assert loaded == reconciliation
    assert reconciliation in uow.yield_reconciliations.list_by_order(order.id)


def test_unit_of_work_rolls_back_on_exception(uow):
    order = _order()
    with pytest.raises(RuntimeError):
        with uow:
            uow.orders.save(order)
            raise RuntimeError("boom")
    fresh_uow = MeatProcessingUnitOfWork(uow.connection)
    assert fresh_uow.orders.get(order.id) is None


def test_unit_of_work_with_outer_owned_transaction_does_not_commit_or_rollback():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    importlib.import_module(
        "migrations.standalone.187_meat_processing_bounded_context_schema"
    ).run(conn)
    order = _order()
    inner = MeatProcessingUnitOfWork(conn, owns_transaction=False)
    with inner:
        inner.orders.save(order)
    # Not committed by the inner UoW — an outer flow owns that; rollback here
    # (without the inner UoW having committed) discards the write.
    conn.rollback()
    outer_check_conn = conn
    assert outer_check_conn.execute(
        "SELECT 1 FROM processing_orders WHERE id=?", (order.id,)).fetchone() is None


def test_outbox_and_processed_events_repositories(uow):
    event_id, operation_id = new_uuid(), new_uuid()
    with uow:
        uow.outbox.enqueue(event_id=event_id, event_name="PROCESSING_ORDER_CREATED",
                            payload_json="{}", operation_id=operation_id)
    pending = uow.outbox.list_pending()
    assert len(pending) == 1
    assert pending[0]["event_id"] == event_id
    uow.outbox.mark_dispatched(pending[0]["id"])
    assert uow.outbox.list_pending() == []

    assert uow.processed_events.was_processed(event_id) is False
    uow.processed_events.mark_processed(event_id, "PROCESSING_ORDER_CREATED", operation_id)
    assert uow.processed_events.was_processed(event_id) is True


def test_authorization_and_audit_log_repositories(uow):
    from backend.domain.meat_processing.value_objects.authorization_grant import (
        AuthorizationGrant,
    )

    grant = AuthorizationGrant(
        permission_code="PRODUCCION.peso.capturar_manual", requested_by=new_uuid(),
        authorized_by=new_uuid(), operation_id=new_uuid(), reason="báscula inestable",
        weight=Decimal("12.5"))
    log_id = uow.authorization_log.record(grant)
    assert log_id

    order_id = new_uuid()
    uow.audit.record(entity_type="ProcessingOrder", entity_id=order_id,
                      action="CREATED", user_id=new_uuid(),
                      processing_order_id=order_id)
    entries = uow.audit.list_for_entity("ProcessingOrder", order_id)
    assert len(entries) == 1
    assert entries[0]["action"] == "CREATED"
