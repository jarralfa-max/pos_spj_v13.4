from decimal import Decimal

from backend.application.losses.execution_context import LossExecutionContext
from backend.application.losses.production_loss import (
    AnalyzeProductionLossCommand, ProductionLossAnalysisService,
    ProductionOutputInput, ProductionYieldCalculator,
)
from backend.shared.ids import new_uuid
from backend.application.event_handlers.losses import ProductionCompletedLossHandler
from backend.domain.products.recipe_enums import OutputType


def test_yield_within_tolerance_is_entirely_normal_loss():
    result = ProductionYieldCalculator().calculate(
        input_weight=Decimal("100"), actual_output_weight=Decimal("89"),
        expected_yield_pct=Decimal("90"), tolerance_pct=Decimal("2"))
    assert result.actual_yield_pct == Decimal("89.00")
    assert result.normal_loss_weight == Decimal("11")
    assert result.abnormal_loss_weight == Decimal("0")


def test_yield_below_tolerance_splits_normal_and_abnormal_loss():
    result = ProductionYieldCalculator().calculate(
        input_weight=Decimal("100"), actual_output_weight=Decimal("84"),
        expected_yield_pct=Decimal("90"), tolerance_pct=Decimal("2"))
    assert result.normal_loss_weight == Decimal("10")
    assert result.abnormal_loss_weight == Decimal("6")
    assert result.is_abnormal is True


def test_declared_waste_is_not_counted_as_productive_output():
    # The calculator receives productive output only; the service performs this filter.
    repo = _Repo(); actor, branch, warehouse = new_uuid(), new_uuid(), new_uuid()
    context = LossExecutionContext(actor, branch, frozenset({branch}), frozenset({warehouse}))
    command = AnalyzeProductionLossCommand(
        new_uuid(), new_uuid(), new_uuid(), new_uuid(), new_uuid(), Decimal("100"),
        (ProductionOutputInput(OUTPUT_ID, Decimal("84")),
         ProductionOutputInput(new_uuid(), Decimal("6"), output_type=OutputType.WASTE)),
        context, warehouse)
    result = ProductionLossAnalysisService(repo, _Auth()).execute(command)
    assert result.abnormal_loss_weight == Decimal("6")


class _Auth:
    def require(self, _actor, _permission): pass


class _Repo:
    def __init__(self): self.saved = None
    def find_processed(self, _op): return None
    def load_context(self, **_ids):
        return {"expected_yield_pct": Decimal("90"), "tolerance_pct": Decimal("2"),
                "normal_classification_id": new_uuid(), "normal_reason_id": new_uuid(),
                "abnormal_classification_id": new_uuid(), "abnormal_reason_id": new_uuid(),
                "primary_output_product_id": OUTPUT_ID}
    def save_analysis(self, **kwargs): self.saved = kwargs


OUTPUT_ID = new_uuid()


def test_service_keeps_recipe_and_profile_versions_in_production_context():
    repo = _Repo(); actor, branch, warehouse = new_uuid(), new_uuid(), new_uuid()
    context = LossExecutionContext(actor, branch, frozenset({branch}), frozenset({warehouse}))
    command = AnalyzeProductionLossCommand(
        operation_id=new_uuid(), production_id=new_uuid(), recipe_version_id=new_uuid(),
        yield_profile_version_id=new_uuid(), input_product_id=new_uuid(),
        input_weight=Decimal("100"), outputs=(ProductionOutputInput(OUTPUT_ID, Decimal("84")),),
        context=context, warehouse_id=warehouse)
    result = ProductionLossAnalysisService(repo, _Auth()).execute(command)
    assert result.abnormal_loss_weight == Decimal("6")
    assert repo.saved["production_id"] == command.production_id
    assert repo.saved["yield_profile_version_id"] == command.yield_profile_version_id


def test_production_event_handler_preserves_decimal_and_version_context():
    class Service:
        command = None
        def execute(self, command): self.command = command; return command
    service = Service(); actor, branch, warehouse = new_uuid(), new_uuid(), new_uuid()
    context = LossExecutionContext(actor, branch, frozenset({branch}), frozenset({warehouse}))
    payload = {"operation_id": new_uuid(), "entity_id": new_uuid(),
               "recipe_version_id": new_uuid(), "yield_profile_version_id": new_uuid(),
               "input_product_id": new_uuid(), "input_weight": "100.000",
               "warehouse_id": warehouse,
               "outputs": [{"product_id": new_uuid(), "weight_kg": "89.500"}]}
    ProductionCompletedLossHandler(service, lambda: context).handle(payload)
    assert service.command.input_weight == Decimal("100.000")
    assert service.command.outputs[0].weight == Decimal("89.500")
