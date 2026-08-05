from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_loss13_has_one_approved_recovery_route():
    service = (ROOT / "backend/application/losses/recovery.py").read_text(encoding="utf-8")
    expiry = (ROOT / "backend/application/losses/expiry_damage.py").read_text(encoding="utf-8")
    assert "class LossRecoveryService" in service
    assert "PENDING_APPROVAL" in service
    assert "APPROVE_RECOVERY" in service
    assert "def record_recovery(" not in expiry
    assert "RecordLotRecoveryCommand" not in expiry


def test_only_rework_releases_quarantine_and_other_recoveries_require_canonical_facts():
    service = (ROOT / "backend/application/losses/recovery.py").read_text(encoding="utf-8")
    repository = (ROOT / "backend/infrastructure/persistence/loss_recovery_repository.py").read_text(encoding="utf-8")
    assert service.count("release_quarantine(") == 1
    assert "validate_reference" in service
    assert "inventory_ledger" in repository
    assert "loss_transfer_claims" in repository
    assert "INSERT INTO inventory_" not in repository


def test_recovery_schema_preserves_decimal_value_and_segregation():
    migration = (ROOT / "migrations/standalone/174_losses_bounded_context_schema.py").read_text(encoding="utf-8")
    assert "approved_by_user_id <> recorded_by_user_id" in migration
    assert "target_product_id" in migration
    assert "PENDING_APPROVAL" in migration
