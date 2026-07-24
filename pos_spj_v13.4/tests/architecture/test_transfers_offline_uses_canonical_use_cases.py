from pathlib import Path


def test_transfers_offline_sync_has_no_database_or_inventory_fallback():
    source = Path("pos_spj_v13.4/backend/application/transfers/offline_sync.py").read_text()
    assert "sqlite3" not in source
    assert "InventoryEngine" not in source
    assert "repositories." not in source
    assert "OfflineTransferOperationExecutor" in source
    assert "operation_hash" in source
    assert "local_sequence" in source
    assert "AGGREGATE_VERSION" in source
