from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_loss10_schema_and_inventory_boundary_are_explicit():
    migration = (ROOT / "migrations/standalone/174_losses_bounded_context_schema.py").read_text(encoding="utf-8")
    service = (ROOT / "backend/application/losses/expiry_damage.py").read_text(encoding="utf-8")
    assert "loss_lot_risk_assessments" in migration
    assert "uq_loss_lot_active_quarantine" in migration
    assert "self._inventory.quarantine(" in service
    assert "self._inventory.release_quarantine(" in service
    assert "self._inventory.dispose_quarantine(" in service
    assert "UPDATE inventory_balances" not in service
