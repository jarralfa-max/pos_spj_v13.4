from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_meat_loss_reads_products_single_source_of_truth():
    source = (ROOT / "backend/infrastructure/persistence/production_loss_repository.py").read_text(encoding="utf-8")
    for table in ("species", "cut_classifications", "cutting_scheme_versions", "cutting_outputs"):
        assert table in source
    for legacy in ("especies", "cortes", "product_recipes", "receta_componentes"):
        assert legacy not in source


def test_meat_observation_schema_lives_only_in_migration():
    migration = (ROOT / "migrations/standalone/174_losses_bounded_context_schema.py").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS loss_meat_output_observations" in migration
    application = (ROOT / "backend/application/losses/production_loss.py").read_text(encoding="utf-8").upper()
    assert "CREATE TABLE" not in application
    assert "ALTER TABLE" not in application


def test_piece_and_weight_values_never_use_float():
    for relative in ("backend/application/losses/production_loss.py",
                     "backend/infrastructure/persistence/production_loss_repository.py"):
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert "float(" not in source
