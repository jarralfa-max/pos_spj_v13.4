from decimal import Decimal

import pytest

from backend.domain.meat_processing.entities.material_requirement import MaterialRequirement
from backend.domain.meat_processing.entities.operator_assignment import OperatorAssignment
from backend.domain.meat_processing.entities.process_incident import ProcessIncident
from backend.domain.meat_processing.entities.process_step_execution import ProcessStepExecution
from backend.domain.meat_processing.enums import (
    ExecutionStatus,
    IncidentStatus,
    IncidentType,
    MaterialRequirementStatus,
    OperatorRole,
)
from backend.domain.meat_processing.exceptions import (
    MeatProcessingInvariantError,
    MeatProcessingStateTransitionError,
)
from backend.shared.ids import new_uuid


# -- MaterialRequirement --------------------------------------------------------

def _requirement(**overrides) -> MaterialRequirement:
    base = dict(id=new_uuid(), operation_id=new_uuid(), processing_order_id=new_uuid(),
                product_id=new_uuid(), required_quantity=Decimal("10"),
                required_weight=Decimal("100"))
    base.update(overrides)
    return MaterialRequirement(**base)


def test_requirement_requires_positive_quantity_or_weight():
    with pytest.raises(MeatProcessingInvariantError):
        _requirement(required_quantity=Decimal("0"), required_weight=Decimal("0"))


def test_requirement_full_lifecycle():
    requirement = _requirement()
    requirement.reserve(quantity=Decimal("10"), weight=Decimal("100"))
    assert requirement.status is MaterialRequirementStatus.RESERVED
    assert requirement.is_fully_reserved
    requirement.allocate(quantity=Decimal("10"), weight=Decimal("100"))
    assert requirement.status is MaterialRequirementStatus.ALLOCATED
    requirement.consume(quantity=Decimal("10"), weight=Decimal("100"))
    assert requirement.status is MaterialRequirementStatus.CONSUMED


def test_requirement_reserve_rejects_overshoot():
    requirement = _requirement()
    with pytest.raises(MeatProcessingInvariantError):
        requirement.reserve(quantity=Decimal("11"), weight=Decimal("0"))


def test_requirement_allocate_before_reserve_rejected():
    requirement = _requirement()
    with pytest.raises(MeatProcessingStateTransitionError):
        requirement.allocate(quantity=Decimal("1"), weight=Decimal("0"))


def test_requirement_allocate_cannot_exceed_reserved():
    requirement = _requirement()
    requirement.reserve(quantity=Decimal("5"), weight=Decimal("50"))
    with pytest.raises(MeatProcessingInvariantError):
        requirement.allocate(quantity=Decimal("6"), weight=Decimal("0"))


def test_requirement_consume_cannot_exceed_allocated():
    requirement = _requirement()
    requirement.reserve(quantity=Decimal("10"), weight=Decimal("100"))
    requirement.allocate(quantity=Decimal("4"), weight=Decimal("40"))
    with pytest.raises(MeatProcessingInvariantError):
        requirement.consume(quantity=Decimal("5"), weight=Decimal("0"))


def test_requirement_cancel_from_required():
    requirement = _requirement()
    requirement.cancel()
    assert requirement.status is MaterialRequirementStatus.CANCELLED
    with pytest.raises(MeatProcessingStateTransitionError):
        requirement.reserve(quantity=Decimal("1"), weight=Decimal("0"))


# -- OperatorAssignment ----------------------------------------------------------

def _assignment(**overrides) -> OperatorAssignment:
    base = dict(id=new_uuid(), operation_id=new_uuid(), processing_order_id=new_uuid(),
                user_id=new_uuid(), role_type=OperatorRole.CUTTER)
    base.update(overrides)
    return OperatorAssignment(**base)


def test_assignment_is_active_until_released():
    assignment = _assignment()
    assert assignment.is_active
    assignment.release()
    assert not assignment.is_active


def test_assignment_cannot_release_twice():
    assignment = _assignment()
    assignment.release()
    with pytest.raises(MeatProcessingStateTransitionError):
        assignment.release()


def test_assignment_requires_canonical_role():
    with pytest.raises(MeatProcessingInvariantError):
        _assignment(role_type="CUTTER")


# -- ProcessStepExecution -----------------------------------------------------

def _step(**overrides) -> ProcessStepExecution:
    base = dict(id=new_uuid(), operation_id=new_uuid(), process_execution_id=new_uuid(),
                step_name="deshuesado")
    base.update(overrides)
    return ProcessStepExecution(**base)


def test_step_lifecycle():
    step = _step()
    assert step.status is ExecutionStatus.NOT_STARTED
    step.start()
    assert step.status is ExecutionStatus.ACTIVE
    step.complete()
    assert step.status is ExecutionStatus.COMPLETED


def test_step_requires_name():
    with pytest.raises(MeatProcessingInvariantError):
        _step(step_name="  ")


def test_step_cannot_complete_before_start():
    step = _step()
    with pytest.raises(MeatProcessingStateTransitionError):
        step.complete()


def test_step_cancel_from_not_started_or_active():
    step = _step()
    step.cancel()
    assert step.status is ExecutionStatus.CANCELLED


# -- ProcessIncident -----------------------------------------------------------

def _incident(**overrides) -> ProcessIncident:
    base = dict(id=new_uuid(), operation_id=new_uuid(), processing_order_id=new_uuid(),
                incident_type=IncidentType.EQUIPMENT_FAILURE, reported_by_user_id=new_uuid(),
                description="Báscula fuera de calibración")
    base.update(overrides)
    return ProcessIncident(**base)


def test_incident_requires_description():
    with pytest.raises(MeatProcessingInvariantError):
        _incident(description=" ")


def test_incident_full_lifecycle():
    incident = _incident()
    assert incident.status is IncidentStatus.OPEN
    incident.start_review()
    assert incident.status is IncidentStatus.UNDER_REVIEW
    incident.resolve(actor_user_id=new_uuid(), resolution_notes="Recalibrada")
    assert incident.status is IncidentStatus.RESOLVED
    incident.close()
    assert incident.status is IncidentStatus.CLOSED


def test_incident_can_resolve_directly_from_open():
    incident = _incident()
    incident.resolve(actor_user_id=new_uuid())
    assert incident.status is IncidentStatus.RESOLVED


def test_incident_cannot_close_before_resolve():
    incident = _incident()
    with pytest.raises(MeatProcessingStateTransitionError):
        incident.close()
