from decimal import Decimal

import pytest

from backend.domain.losses.entities.loss_case import LossCase
from backend.domain.losses.entities.loss_line import LossLine
from backend.domain.losses.enums import LossClassificationCode, LossOrigin, LossStatus
from backend.domain.losses.exceptions import LossInvariantError, LossStateTransitionError
from backend.shared.ids import new_uuid


def _line(**changes):
    values = {
        "id": new_uuid(), "product_id": new_uuid(),
        "quantity": Decimal("2"), "weight": Decimal("1.750"), "unit": "kg",
    }
    values.update(changes)
    return LossLine(**values)


def _case(**changes):
    values = {
        "id": new_uuid(), "operation_id": new_uuid(), "branch_id": new_uuid(),
        "warehouse_id": new_uuid(), "reported_by_user_id": new_uuid(),
        "classification": LossClassificationCode.EXPIRY,
        "origin": LossOrigin.INVENTORY, "reason_id": new_uuid(),
    }
    values.update(changes)
    return LossCase(**values)


def test_loss_line_accepts_pieces_and_weight_as_decimal():
    line = _line()
    assert line.quantity == Decimal("2")
    assert line.weight == Decimal("1.750")


@pytest.mark.parametrize("field", ["quantity", "weight", "unit_cost", "recoverable_value"])
def test_loss_line_rejects_float(field):
    with pytest.raises(TypeError, match="Decimal"):
        _line(**{field: 1.5})


def test_loss_line_requires_positive_quantity_or_weight():
    with pytest.raises(LossInvariantError):
        _line(quantity=Decimal("0"), weight=Decimal("0"))


def test_loss_case_workflow_is_explicit_and_protected():
    case = _case()
    case.add_line(_line())
    case.submit(actor_user_id=new_uuid())
    assert case.status is LossStatus.SUBMITTED
    case.start_review(actor_user_id=new_uuid())
    case.approve(actor_user_id=new_uuid())
    case.mark_inventory_posted(movement_id=new_uuid())
    case.close(actor_user_id=new_uuid())
    assert case.status is LossStatus.CLOSED


def test_loss_case_cannot_submit_without_lines():
    with pytest.raises(LossInvariantError, match="línea"):
        _case().submit(actor_user_id=new_uuid())


def test_loss_case_cannot_skip_review_and_approval():
    case = _case()
    case.add_line(_line())
    with pytest.raises(LossStateTransitionError):
        case.approve(actor_user_id=new_uuid())


def test_loss_case_identity_is_distinct_from_operation():
    case = _case()
    assert case.id != case.operation_id
