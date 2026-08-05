from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_losses_application_does_not_write_inventory_tables_directly():
    source = (ROOT / "backend/application/losses/loss_inventory_integration.py").read_text(
        encoding="utf-8").upper()
    assert "UPDATE INVENTORY_" not in source
    assert "INSERT INTO INVENTORY_" not in source
    assert "POSTINVENTORYMOVEMENTUSECASE" not in source
    assert "LOSSESINVENTORYGATEWAY" not in source


def test_reverse_inventory_use_case_supports_outer_atomic_transaction():
    source = (ROOT / "backend/application/inventory/use_cases/reverse_inventory_movement.py").read_text(
        encoding="utf-8")
    assert "owns_transaction: bool = True" in source
    assert "InventoryUnitOfWork(connection, owns_transaction=owns_transaction)" in source
