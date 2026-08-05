from decimal import Decimal

from backend.application.losses.register_general_loss import (
    GeneralLossLineInput,
    RegisterGeneralLossCommand,
    RegisterGeneralLossUseCase,
)
from backend.application.losses.execution_context import LossExecutionContext
from backend.domain.losses.enums import LossOrigin, LossStatus
from backend.shared.ids import new_uuid


class _Authorization:
    def require(self, _user_id, permission):
        assert permission in {"LOSSES_REPORT", "LOSSES_SUBMIT"}


class _Repository:
    def __init__(self):
        self.saved = None

    def find_processed(self, _operation_id):
        return None

    def resolve_reason(self, _classification_id, _reason_id):
        return "HANDLING_DAMAGE", False

    def save(self, case, evidence, event):
        self.saved = case, evidence, event


def _command(*, submit=True):
    branch, warehouse = new_uuid(), new_uuid()
    context = LossExecutionContext(
        actor_user_id=new_uuid(), active_branch_id=branch,
        assigned_branch_ids=frozenset({branch}),
        allowed_warehouse_ids=frozenset({warehouse}),
    )
    return RegisterGeneralLossCommand(
        operation_id=new_uuid(), context=context, warehouse_id=warehouse,
        classification_id=new_uuid(), reason_id=new_uuid(),
        origin=LossOrigin.INVENTORY,
        lines=(GeneralLossLineInput(
            product_id=new_uuid(), quantity=Decimal("2.500"),
            weight=Decimal("0"), unit="unit",
        ),), submit=submit,
    )


def test_registers_exact_decimal_and_submits_without_posting_inventory():
    repository = _Repository()
    result = RegisterGeneralLossUseCase(repository, _Authorization()).execute(_command())

    case, _evidence, event = repository.saved
    assert result.status is LossStatus.SUBMITTED
    assert case.lines[0].quantity == Decimal("2.500")
    assert case.inventory_movement_id is None
    assert event["event_name"] == "LOSS_CASE_SUBMITTED"


def test_draft_stays_editable():
    repository = _Repository()
    result = RegisterGeneralLossUseCase(repository, _Authorization()).execute(
        _command(submit=False))
    assert result.status is LossStatus.DRAFT

