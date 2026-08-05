from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_loss12_consumes_transfer_facts_without_posting_inventory_twice():
    service = (ROOT / "backend/application/losses/transfer_integration.py").read_text(encoding="utf-8")
    repository = (ROOT / "backend/infrastructure/persistence/transfer_loss_repository.py").read_text(encoding="utf-8")
    assert "inventory_receipt_posted" in service
    assert "POSTED_BY_TRANSFER_RECEIPT" in service
    assert "self._inventory" not in service
    assert "INSERT INTO inventory_" not in repository
    assert "UPDATE inventory_" not in repository


def test_transfer_loss_gateway_is_wired_to_the_existing_transfer_handler():
    factory = (ROOT / "backend/infrastructure/desktop/losses_factory.py").read_text(encoding="utf-8")
    assert "TransferLossCaseRequestedHandler" in factory
    assert "TransferLossIntegrationService" in factory


def test_transfer_claims_and_responsibility_live_in_the_loss_migration():
    migration = (ROOT / "migrations/standalone/174_losses_bounded_context_schema.py").read_text(encoding="utf-8")
    assert "loss_transfer_links" in migration
    assert "loss_transfer_claims" in migration
    assert "POSTED_BY_TRANSFER_RECEIPT" in migration
