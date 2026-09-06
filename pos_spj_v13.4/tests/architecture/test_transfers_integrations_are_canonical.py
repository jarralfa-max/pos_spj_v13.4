from pathlib import Path
from tests.architecture.architecture_guardrails import APP_ROOT


def test_transfer_integrations_have_no_legacy_or_direct_engine_fallbacks():
    root = (APP_ROOT / "backend/application/transfers/integrations")
    source = "\n".join(path.read_text() for path in root.glob("*.py"))

    assert "sqlite3" not in source
    assert "InventoryEngine" not in source
    assert "core.services" not in source
    assert "repositories.transferencias" not in source
    assert "CanonicalInventoryTransferGateway" in source
    assert "ReserveInventoryUseCase" in source
    assert "PostTransferDispatchUseCase" in source
    assert "PostTransferReceiptUseCase" in source
    assert "ProductUnitConversionQueryService" in source
    assert "ProductCatchWeightQueryService" in source
    assert "ProductQualityProfileQueryService" in source
    assert "ProductShelfLifeQueryService" in source
