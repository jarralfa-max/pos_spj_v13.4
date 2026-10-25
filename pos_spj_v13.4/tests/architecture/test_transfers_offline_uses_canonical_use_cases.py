from tests.architecture.architecture_guardrails import APP_ROOT


def test_offline_reception_lives_in_the_single_central_ingestion():
    """Slice 4 híbrido: el receptor propio de Transferencias (`offline_sync.py`) se
    consolidó en la ingesta central única. Sus garantías (secuencia, huella,
    versión del agregado) siguen exigidas, ahora para todos los contextos, y la
    ingesta no toca la base ni el inventario directamente: usa su puerto."""
    assert not (APP_ROOT / "backend/application/transfers/offline_sync.py").exists()
    source = (APP_ROOT / "backend/application/sync/central_ingestion.py").read_text(
        encoding="utf-8")
    assert "sqlite3" not in source
    assert "InventoryEngine" not in source
    assert "repositories." not in source
    assert "class CentralInboxRepository(Protocol)" in source
    for regla in ("SEQUENCE_REUSED", "EVENT_ID_REUSED", "AGGREGATE_VERSION_REGRESSION"):
        assert regla in source
