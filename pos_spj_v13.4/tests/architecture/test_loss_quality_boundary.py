from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_loss11_uses_inventory_quality_routes_and_immutable_evidence():
    service = (ROOT / "backend/application/losses/quality_control.py").read_text(encoding="utf-8")
    repository = (ROOT / "backend/infrastructure/persistence/quality_control_repository.py").read_text(encoding="utf-8")
    migration = (ROOT / "migrations/standalone/174_losses_bounded_context_schema.py").read_text(encoding="utf-8")
    assert "self._inventory.record_temperature(" in service
    assert "self._inventory.quarantine(" in service
    assert "self._inventory.dispose_quarantine(" not in service
    assert "UPDATE inventory_" not in repository
    assert "loss_quality_assessments" in migration
    assert "loss_quality_evidence" in migration
    assert "inventory_quarantines" not in migration
    assert "inventory_quarantine(id)" in migration
    assert "checksum" in repository


def test_quality_permissions_are_granular():
    permissions = (ROOT / "backend/application/losses/permissions.py").read_text(encoding="utf-8")
    assert "LOSSES_QUALITY_REJECT" in permissions
    assert "LOSSES_QUALITY_CONDEMN" in permissions
