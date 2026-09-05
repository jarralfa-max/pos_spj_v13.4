from decimal import Decimal

import pytest

from backend.domain.meat_processing.entities.production_plan import ProductionPlan
from backend.domain.meat_processing.entities.production_plan_line import ProductionPlanLine
from backend.domain.meat_processing.enums import PlanSourceType, ProductionPlanStatus
from backend.domain.meat_processing.exceptions import (
    MeatProcessingInvariantError,
    MeatProcessingSegregationOfDutiesError,
    MeatProcessingStateTransitionError,
)
from backend.shared.ids import new_uuid


# -- ProductionPlanLine -------------------------------------------------------

def _line(**overrides) -> ProductionPlanLine:
    base = dict(
        id=new_uuid(), product_id=new_uuid(), source_type=PlanSourceType.FORECAST,
        planned_quantity=Decimal("10"), planned_weight=Decimal("100"),
    )
    base.update(overrides)
    return ProductionPlanLine(**base)


def test_line_requires_positive_quantity_or_weight():
    with pytest.raises(MeatProcessingInvariantError):
        _line(planned_quantity=Decimal("0"), planned_weight=Decimal("0"))


def test_line_rejects_float():
    with pytest.raises(TypeError):
        _line(planned_quantity=10.0)


def test_line_record_conversion_accumulates_and_tracks_orders():
    line = _line()
    order_1, order_2 = new_uuid(), new_uuid()
    line.record_conversion(processing_order_id=order_1, converted_quantity=Decimal("4"),
                            converted_weight=Decimal("40"))
    line.record_conversion(processing_order_id=order_2, converted_quantity=Decimal("6"),
                            converted_weight=Decimal("60"))
    assert line.converted_quantity == Decimal("10")
    assert line.converted_weight == Decimal("100")
    assert line.converted_processing_order_ids == (order_1, order_2)
    assert line.is_fully_converted
    assert line.remaining_quantity == Decimal("0")


def test_line_record_conversion_rejects_overshoot():
    line = _line()
    with pytest.raises(MeatProcessingInvariantError):
        line.record_conversion(processing_order_id=new_uuid(),
                                converted_quantity=Decimal("11"), converted_weight=Decimal("0"))


def test_line_partial_conversion_state():
    line = _line()
    line.record_conversion(processing_order_id=new_uuid(), converted_quantity=Decimal("3"),
                            converted_weight=Decimal("30"))
    assert line.is_partially_converted
    assert not line.is_fully_converted


def test_line_same_order_id_recorded_once():
    line = _line()
    order_id = new_uuid()
    line.record_conversion(processing_order_id=order_id, converted_quantity=Decimal("5"),
                            converted_weight=Decimal("50"))
    line.record_conversion(processing_order_id=order_id, converted_quantity=Decimal("5"),
                            converted_weight=Decimal("50"))
    assert line.converted_processing_order_ids == (order_id,)


# -- ProductionPlan ------------------------------------------------------------

def _plan(**overrides) -> ProductionPlan:
    base = dict(
        id=new_uuid(), operation_id=new_uuid(), branch_id=new_uuid(),
        planning_period="2026-08", created_by_user_id=new_uuid(),
    )
    base.update(overrides)
    return ProductionPlan(**base)


def test_plan_requires_planning_period():
    with pytest.raises(MeatProcessingInvariantError):
        _plan(planning_period="  ")


def test_plan_rejects_equal_id_and_operation_id():
    same = new_uuid()
    with pytest.raises(MeatProcessingInvariantError):
        _plan(id=same, operation_id=same)


def test_plan_full_lifecycle_happy_path():
    creator = new_uuid()
    plan = _plan(created_by_user_id=creator)
    assert plan.status is ProductionPlanStatus.DRAFT

    plan.add_line(_line())
    plan.generate()
    assert plan.status is ProductionPlanStatus.GENERATED

    plan.submit_for_review()
    assert plan.status is ProductionPlanStatus.UNDER_REVIEW

    plan.approve(actor_user_id=new_uuid())
    assert plan.status is ProductionPlanStatus.APPROVED


def test_plan_cannot_generate_without_lines():
    plan = _plan()
    with pytest.raises(MeatProcessingInvariantError):
        plan.generate()


def test_plan_creator_cannot_approve_own_plan():
    creator = new_uuid()
    plan = _plan(created_by_user_id=creator)
    plan.add_line(_line())
    plan.generate()
    plan.submit_for_review()
    with pytest.raises(MeatProcessingSegregationOfDutiesError):
        plan.approve(actor_user_id=creator)


def test_plan_rejects_illegal_transition():
    plan = _plan()
    with pytest.raises(MeatProcessingStateTransitionError):
        plan.approve(actor_user_id=new_uuid())


def test_plan_cannot_add_line_after_review_started():
    plan = _plan()
    plan.add_line(_line())
    plan.generate()
    plan.submit_for_review()
    with pytest.raises(MeatProcessingStateTransitionError):
        plan.add_line(_line())


def test_plan_convert_line_updates_plan_status_to_partially_then_fully_converted():
    plan = _plan()
    line_a, line_b = _line(), _line()
    plan.add_line(line_a)
    plan.add_line(line_b)
    plan.generate()
    plan.submit_for_review()
    plan.approve(actor_user_id=new_uuid())

    plan.convert_line(line_a.id, processing_order_id=new_uuid(),
                       converted_quantity=Decimal("10"), converted_weight=Decimal("100"))
    assert plan.status is ProductionPlanStatus.PARTIALLY_CONVERTED
    assert not plan.is_fully_converted

    plan.convert_line(line_b.id, processing_order_id=new_uuid(),
                       converted_quantity=Decimal("10"), converted_weight=Decimal("100"))
    assert plan.status is ProductionPlanStatus.CONVERTED
    assert plan.is_fully_converted


def test_plan_cannot_convert_before_approval():
    plan = _plan()
    line = _line()
    plan.add_line(line)
    with pytest.raises(MeatProcessingStateTransitionError):
        plan.convert_line(line.id, processing_order_id=new_uuid(),
                           converted_quantity=Decimal("1"), converted_weight=Decimal("0"))


def test_plan_convert_line_unknown_id_raises():
    plan = _plan()
    plan.add_line(_line())
    plan.generate()
    plan.submit_for_review()
    plan.approve(actor_user_id=new_uuid())
    with pytest.raises(MeatProcessingInvariantError):
        plan.convert_line(new_uuid(), processing_order_id=new_uuid(),
                           converted_quantity=Decimal("1"), converted_weight=Decimal("0"))


def test_plan_cancel_from_any_non_terminal_state():
    plan = _plan()
    plan.cancel()
    assert plan.status is ProductionPlanStatus.CANCELLED
    with pytest.raises(MeatProcessingStateTransitionError):
        plan.cancel()
