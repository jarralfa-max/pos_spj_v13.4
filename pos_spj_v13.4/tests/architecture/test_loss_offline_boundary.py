from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_loss_offline_has_explicit_application_and_infrastructure_boundaries():
    application = (ROOT / "backend/application/losses/offline.py").read_text(encoding="utf-8")
    repository = (ROOT / "backend/infrastructure/persistence/loss_offline_repository.py").read_text(encoding="utf-8")
    assert "class LossOfflineDraftService" in application
    assert "class LossOfflineSyncService" in application
    assert "class SQLiteLossOfflineRepository" in repository
    assert "CREATE TABLE" not in application
    assert "CREATE TABLE" not in repository
    assert "PyQt5" not in application + repository


def test_loss_offline_schema_uses_uuid_and_separates_sync_outbox_from_domain_outbox():
    migration = (ROOT / "migrations/standalone/174_losses_bounded_context_schema.py").read_text(encoding="utf-8")
    for table in ("loss_offline_drafts", "loss_offline_evidence",
                  "loss_sync_outbox", "loss_sync_conflicts"):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in migration
    assert "operation_id TEXT NOT NULL UNIQUE" in migration
    assert "loss_outbox" in migration and "loss_sync_outbox" in migration
