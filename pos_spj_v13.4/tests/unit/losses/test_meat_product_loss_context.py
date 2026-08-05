from decimal import Decimal

from backend.application.losses.execution_context import LossExecutionContext
from backend.application.losses.production_loss import AnalyzeProductionLossCommand, ProductionLossAnalysisService, ProductionOutputInput
from backend.domain.losses.exceptions import LossInvariantError
from backend.domain.products.entities.cutting_output import MeasureKind
from backend.domain.products.recipe_enums import OutputType
from backend.shared.ids import new_uuid


class _Allow:
    def require(self, _actor, _permission): pass


class _Repo:
    def __init__(self, config): self.config = config; self.saved = None
    def find_processed(self, _operation): return None
    def load_context(self, **_kwargs): return self.config
    def save_analysis(self, **kwargs): self.saved = kwargs


def _context():
    actor, branch, warehouse = new_uuid(), new_uuid(), new_uuid()
    return LossExecutionContext(actor, branch, frozenset({branch}), frozenset({warehouse})), warehouse


def _config(species, main_product, by_product, main_cut, by_cut):
    return {"expected_yield_pct": Decimal("90"), "tolerance_pct": Decimal("2"),
            "normal_reason_id": new_uuid(), "abnormal_reason_id": new_uuid(),
            "primary_output_product_id": main_product,
            "output_product_ids": frozenset({main_product, by_product}),
            "meat_output_config": {
                main_product: {"species_id": species, "output_type": "MAIN_PRODUCT",
                               "measure_kind": "BY_PIECE", "cut_classification_id": main_cut},
                by_product: {"species_id": species, "output_type": "BY_PRODUCT",
                             "measure_kind": "BY_WEIGHT", "cut_classification_id": by_cut}}}


def test_meat_cutting_preserves_species_cuts_pieces_weight_and_by_product_role():
    species, main, by_product, main_cut, by_cut = (new_uuid() for _ in range(5))
    repo = _Repo(_config(species, main, by_product, main_cut, by_cut))
    context, warehouse = _context()
    command = AnalyzeProductionLossCommand(
        new_uuid(), new_uuid(), new_uuid(), new_uuid(), new_uuid(), Decimal("100"),
        (ProductionOutputInput(main, Decimal("70"), output_type=OutputType.MAIN_PRODUCT,
                               quantity=Decimal("7"), species_id=species,
                               cut_classification_id=main_cut, measure_kind=MeasureKind.BY_PIECE),
         ProductionOutputInput(by_product, Decimal("14"), output_type=OutputType.BY_PRODUCT,
                               species_id=species, cut_classification_id=by_cut,
                               measure_kind=MeasureKind.BY_WEIGHT)),
        context, warehouse, new_uuid())
    result = ProductionLossAnalysisService(repo, _Allow()).execute(command)
    assert result.abnormal_loss_weight == Decimal("6")
    assert repo.saved["outputs"][0].quantity == Decimal("7")
    assert repo.saved["outputs"][1].output_type is OutputType.BY_PRODUCT


def test_cross_species_cut_fails_closed():
    species, main, by_product, main_cut, by_cut = (new_uuid() for _ in range(5))
    repo = _Repo(_config(species, main, by_product, main_cut, by_cut))
    context, warehouse = _context()
    command = AnalyzeProductionLossCommand(
        new_uuid(), new_uuid(), new_uuid(), new_uuid(), new_uuid(), Decimal("100"),
        (ProductionOutputInput(main, Decimal("84"), species_id=new_uuid(),
                               cut_classification_id=main_cut,
                               measure_kind=MeasureKind.BY_PIECE),),
        context, warehouse, new_uuid())
    try:
        ProductionLossAnalysisService(repo, _Allow()).execute(command)
    except LossInvariantError:
        return
    raise AssertionError("Una especie ajena debía fallar cerrado")
