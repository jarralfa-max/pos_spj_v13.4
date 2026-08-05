from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_registration_page_uses_canonical_components_and_has_no_sql():
    source = (ROOT / "frontend/desktop/modules/losses/pages/loss_registration_page.py").read_text(
        encoding="utf-8")
    for component in ("ProductSearchBox", "QuantityInput", "DecimalInput", "FilePathInput"):
        assert component in source
    assert "SELECT " not in source.upper()
    assert "sqlite" not in source.lower()


def test_factory_no_longer_loads_legacy_merma_module():
    source = (ROOT / "backend/infrastructure/desktop/losses_factory.py").read_text(
        encoding="utf-8")
    assert "modulos.merma" not in source
    assert "LegacyLossRegistrationBridge" not in source

