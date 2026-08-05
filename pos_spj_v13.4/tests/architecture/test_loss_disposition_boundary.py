from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_loss14_is_the_only_quality_disposal_route():
    service = (ROOT / "backend/application/losses/disposition.py").read_text(encoding="utf-8")
    quality = (ROOT / "backend/application/losses/quality_control.py").read_text(encoding="utf-8")
    expiry = (ROOT / "backend/application/losses/expiry_damage.py").read_text(encoding="utf-8")
    repository = (ROOT / "backend/infrastructure/persistence/loss_disposition_repository.py").read_text(encoding="utf-8")
    assert service.count("self._inventory.dispose_quarantine(") == 1
    assert "self._inventory.dispose_quarantine(" not in quality
    assert "self._inventory.dispose_quarantine(" not in expiry
    assert "UPDATE inventory_" not in repository
    assert "INSERT INTO inventory_" not in repository


def test_loss14_schema_preserves_confirmations_evidence_and_certificate():
    migration = (ROOT / "migrations/standalone/174_losses_bounded_context_schema.py").read_text(encoding="utf-8")
    for field in ("planned_by_user_id", "authorized_by_user_id", "completed_by_user_id",
                  "authorization_operation_id", "completion_operation_id",
                  "certificate_required", "certificate_reference",
                  "loss_disposition_evidence"):
        assert field in migration
