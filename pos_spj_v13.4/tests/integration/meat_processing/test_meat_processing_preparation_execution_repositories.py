import importlib
import sqlite3
from decimal import Decimal

import pytest

from backend.domain.meat_processing.entities.material_requirement import MaterialRequirement
from backend.domain.meat_processing.entities.operator_assignment import OperatorAssignment
from backend.domain.meat_processing.entities.process_incident import ProcessIncident
from backend.domain.meat_processing.entities.process_step_execution import ProcessStepExecution
from backend.domain.meat_processing.entities.processing_order import ProcessingOrder
from backend.domain.meat_processing.enums import (
    IncidentType,
    OperatorRole,
    ProcessType,
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
        "migrations.standalone.187_meat_processing_bounded_context_schema").run(conn)
    importlib.import_module(
        "migrations.standalone.248_meat_processing_preparation_execution_schema").run(conn)
    return MeatProcessingUnitOfWork(conn)


def _order(**overrides) -> ProcessingOrder:
    base = dict(
        id=new_uuid(), operation_id=new_uuid(), branch_id=new_uuid(),
        warehouse_id=new_uuid(), process_type=ProcessType.CUTTING,
        target_product_id=new_uuid(), created_by_user_id=new_uuid(),
        planned_quantity=Decimal("10"), planned_weight=Decimal("100"))
    base.update(overrides)
    return ProcessingOrder(**base)


def test_material_requirement_round_trips_through_lifecycle(uow):
    order = _order()
    with uow:
        uow.orders.save(order)
    requirement = MaterialRequirement(
        id=new_uuid(), operation_id=new_uuid(), processing_order_id=order.id,
        product_id=new_uuid(), required_quantity=Decimal("10"), required_weight=Decimal("100"))
    requirement.reserve(quantity=Decimal("6"), weight=Decimal("60"))
    with uow:
        uow.material_requirements.save(requirement)
    loaded = uow.material_requirements.get(requirement.id)
    assert loaded == requirement
    assert requirement in uow.material_requirements.list_by_order(order.id)

    loaded.allocate(quantity=Decimal("6"), weight=Decimal("60"))
    with uow:
        uow.material_requirements.save(loaded)
    assert uow.material_requirements.get(requirement.id).status.value == "ALLOCATED"


def test_operator_assignment_round_trips_and_release(uow):
    order = _order()
    with uow:
        uow.orders.save(order)
    assignment = OperatorAssignment(
        id=new_uuid(), operation_id=new_uuid(), processing_order_id=order.id,
        user_id=new_uuid(), role_type=OperatorRole.CUTTER)
    with uow:
        uow.operator_assignments.save(assignment)
    assert uow.operator_assignments.get(assignment.id) == assignment
    assert assignment in uow.operator_assignments.list_active_by_order(order.id)

    assignment.release()
    with uow:
        uow.operator_assignments.save(assignment)
    assert uow.operator_assignments.list_active_by_order(order.id) == []
    assert uow.operator_assignments.get(assignment.id).released_at is not None


def test_process_step_execution_round_trips(uow):
    order = _order()
    with uow:
        uow.orders.save(order)
    execution_id = new_uuid()
    with uow:
        from backend.domain.meat_processing.entities.process_execution import ProcessExecution
        execution = ProcessExecution(
            id=execution_id, operation_id=new_uuid(), processing_order_id=order.id)
        uow.executions.save(execution)
    step = ProcessStepExecution(
        id=new_uuid(), operation_id=new_uuid(), process_execution_id=execution_id,
        step_name="deshuesado", sequence=1)
    step.start()
    with uow:
        uow.steps.save(step)
    loaded = uow.steps.get(step.id)
    assert loaded == step
    assert step in uow.steps.list_by_execution(execution_id)


def test_process_incident_round_trips_and_resolves(uow):
    order = _order()
    with uow:
        uow.orders.save(order)
    incident = ProcessIncident(
        id=new_uuid(), operation_id=new_uuid(), processing_order_id=order.id,
        incident_type=IncidentType.EQUIPMENT_FAILURE, reported_by_user_id=new_uuid(),
        description="Báscula descalibrada")
    with uow:
        uow.incidents.save(incident)
    loaded = uow.incidents.get(incident.id)
    assert loaded == incident
    assert incident in uow.incidents.list_by_order(order.id)

    loaded.resolve(actor_user_id=new_uuid(), resolution_notes="Recalibrada")
    with uow:
        uow.incidents.save(loaded)
    persisted = uow.incidents.get(incident.id)
    assert persisted.status.value == "RESOLVED"
    assert persisted.resolution_notes == "Recalibrada"
