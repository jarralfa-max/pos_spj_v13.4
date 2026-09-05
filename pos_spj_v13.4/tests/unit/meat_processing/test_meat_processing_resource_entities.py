from decimal import Decimal

import pytest

from backend.domain.meat_processing.entities.equipment_assignment import EquipmentAssignment
from backend.domain.meat_processing.entities.production_area import ProductionArea
from backend.domain.meat_processing.entities.production_equipment import ProductionEquipment
from backend.domain.meat_processing.entities.production_station import ProductionStation
from backend.domain.meat_processing.entities.work_center import WorkCenter
from backend.domain.meat_processing.enums import EquipmentStatus
from backend.domain.meat_processing.exceptions import (
    MeatProcessingInvariantError,
    MeatProcessingStateTransitionError,
)
from backend.shared.ids import new_uuid


# -- ProductionArea ----------------------------------------------------------

def _area(**overrides) -> ProductionArea:
    base = dict(
        id=new_uuid(), branch_id=new_uuid(), warehouse_id=new_uuid(), code="DESP",
        name="Despiece")
    base.update(overrides)
    return ProductionArea(**base)


def test_area_requires_code_and_name():
    with pytest.raises(MeatProcessingInvariantError):
        _area(code="  ")
    with pytest.raises(MeatProcessingInvariantError):
        _area(name="")


def test_area_activate_deactivate():
    area = _area()
    assert area.is_active
    area.deactivate()
    assert not area.is_active
    area.activate()
    assert area.is_active


# -- WorkCenter ----------------------------------------------------------------

def _work_center(**overrides) -> WorkCenter:
    base = dict(id=new_uuid(), production_area_id=new_uuid(), code="WC1", name="Centro 1")
    base.update(overrides)
    return WorkCenter(**base)


def test_work_center_rejects_negative_capacity():
    with pytest.raises(MeatProcessingInvariantError):
        _work_center(capacity_per_hour=Decimal("-1"))


def test_work_center_rejects_unknown_basis():
    with pytest.raises(MeatProcessingInvariantError):
        _work_center(capacity_basis="pieces")


def test_work_center_rejects_float_capacity():
    with pytest.raises(TypeError):
        _work_center(capacity_per_hour=1.5)


def test_work_center_defaults():
    wc = _work_center()
    assert wc.capacity_per_hour == Decimal("0")
    assert wc.capacity_basis == "weight"
    assert wc.is_active


# -- ProductionStation -----------------------------------------------------------

def test_station_requires_code_and_name():
    with pytest.raises(MeatProcessingInvariantError):
        ProductionStation(id=new_uuid(), work_center_id=new_uuid(), code="", name="Linea 1")


# -- ProductionEquipment ---------------------------------------------------------

def _equipment(**overrides) -> ProductionEquipment:
    base = dict(
        id=new_uuid(), work_center_id=new_uuid(), code="EQ1", name="Sierra",
        equipment_type="SAW")
    base.update(overrides)
    return ProductionEquipment(**base)


def test_equipment_requires_type():
    with pytest.raises(MeatProcessingInvariantError):
        _equipment(equipment_type="  ")


def test_equipment_starts_available():
    equipment = _equipment()
    assert equipment.status is EquipmentStatus.AVAILABLE
    assert equipment.is_available


def test_equipment_maintenance_lifecycle():
    equipment = _equipment()
    equipment.start_maintenance()
    assert equipment.status is EquipmentStatus.MAINTENANCE
    assert not equipment.is_available
    equipment.complete_maintenance()
    assert equipment.status is EquipmentStatus.AVAILABLE
    assert equipment.last_maintenance_at is not None


def test_equipment_cannot_start_maintenance_twice():
    equipment = _equipment()
    equipment.start_maintenance()
    with pytest.raises(MeatProcessingStateTransitionError):
        equipment.start_maintenance()


def test_equipment_cannot_complete_maintenance_when_not_in_maintenance():
    equipment = _equipment()
    with pytest.raises(MeatProcessingStateTransitionError):
        equipment.complete_maintenance()


def test_equipment_retire_is_terminal():
    equipment = _equipment()
    equipment.retire()
    assert equipment.status is EquipmentStatus.RETIRED
    with pytest.raises(MeatProcessingStateTransitionError):
        equipment.retire()


def test_equipment_can_retire_from_maintenance():
    equipment = _equipment()
    equipment.start_maintenance()
    equipment.retire()
    assert equipment.status is EquipmentStatus.RETIRED


# -- EquipmentAssignment ---------------------------------------------------------

def _assignment(**overrides) -> EquipmentAssignment:
    base = dict(
        id=new_uuid(), operation_id=new_uuid(), processing_order_id=new_uuid(),
        equipment_id=new_uuid())
    base.update(overrides)
    return EquipmentAssignment(**base)


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


def test_assignment_rejects_same_id_and_operation_id():
    shared = new_uuid()
    with pytest.raises(MeatProcessingInvariantError):
        _assignment(id=shared, operation_id=shared)
