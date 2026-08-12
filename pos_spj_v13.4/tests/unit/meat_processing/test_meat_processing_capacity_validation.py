from decimal import Decimal

import pytest

from backend.domain.meat_processing.entities.production_plan_line import ProductionPlanLine
from backend.domain.meat_processing.enums import PlanSourceType
from backend.domain.meat_processing.exceptions import MeatProcessingInvariantError
from backend.domain.meat_processing.services.capacity_validation_service import (
    CapacityValidationService,
)
from backend.shared.ids import new_uuid


def _line(quantity, weight) -> ProductionPlanLine:
    return ProductionPlanLine(
        id=new_uuid(), product_id=new_uuid(), source_type=PlanSourceType.MANUAL,
        planned_quantity=Decimal(quantity), planned_weight=Decimal(weight))


def test_validate_sums_weight_by_default_and_reports_within_capacity():
    lines = [_line("5", "50"), _line("3", "30")]
    result = CapacityValidationService.validate(lines, capacity_limit=Decimal("100"))
    assert result.basis == "weight"
    assert result.planned_load == Decimal("80")
    assert result.within_capacity is True
    assert result.overage == Decimal("0")


def test_validate_detects_overage_and_computes_utilization():
    lines = [_line("5", "70"), _line("3", "50")]
    result = CapacityValidationService.validate(lines, capacity_limit=Decimal("100"))
    assert result.within_capacity is False
    assert result.overage == Decimal("20")
    assert result.utilization_pct == Decimal("120")


def test_validate_can_use_quantity_basis():
    lines = [_line("40", "1"), _line("40", "1")]
    result = CapacityValidationService.validate(
        lines, capacity_limit=Decimal("100"), basis="quantity")
    assert result.planned_load == Decimal("80")
    assert result.within_capacity is True


def test_validate_rejects_negative_capacity_limit():
    with pytest.raises(MeatProcessingInvariantError):
        CapacityValidationService.validate([], capacity_limit=Decimal("-1"))


def test_validate_rejects_unknown_basis():
    with pytest.raises(MeatProcessingInvariantError):
        CapacityValidationService.validate([], capacity_limit=Decimal("10"), basis="hours")


def test_validate_zero_capacity_limit_has_no_utilization_pct():
    result = CapacityValidationService.validate([], capacity_limit=Decimal("0"))
    assert result.utilization_pct is None
    assert result.within_capacity is True
