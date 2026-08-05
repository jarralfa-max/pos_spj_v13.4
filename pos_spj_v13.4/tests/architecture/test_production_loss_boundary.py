from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_production_loss_uses_only_canonical_recipe_and_yield_tables():
    source = (ROOT / "backend/infrastructure/persistence/production_loss_repository.py").read_text(encoding="utf-8")
    assert "recipe_versions" in source and "yield_profile_versions" in source
    assert "product_recipes" not in source
    assert "receta_componentes" not in source
    assert "float(" not in source


def test_loss_calculation_stays_out_of_production_ui_and_infrastructure():
    source = (ROOT / "backend/application/losses/production_loss.py").read_text(encoding="utf-8")
    assert "class ProductionYieldCalculator" in source
    assert "SELECT " not in source.upper()
    assert "INSERT " not in source.upper()
