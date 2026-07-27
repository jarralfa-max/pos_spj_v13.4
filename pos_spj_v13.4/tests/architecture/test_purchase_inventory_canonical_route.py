from __future__ import annotations

from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PURCHASE_SERVICE = PACKAGE_ROOT / "core" / "services" / "purchase_service.py"
RECEIVE_PO_ADAPTER = PACKAGE_ROOT / "application" / "purchases" / "receive_po_adapter.py"
APP_CONTAINER = PACKAGE_ROOT / "core" / "app_container.py"


def test_purchase_and_reception_use_canonical_inventory_service() -> None:
    purchase_source = PURCHASE_SERVICE.read_text(encoding="utf-8")
    reception_source = RECEIVE_PO_ADAPTER.read_text(encoding="utf-8")
    container_source = APP_CONTAINER.read_text(encoding="utf-8")

    assert "increase_stock(" in purchase_source
    assert "decrease_stock(" in purchase_source
    assert "increase_stock(" in reception_source
    assert "InventoryApplicationService" in container_source
    assert "InventoryRepository" in container_source


def test_purchase_and_reception_do_not_use_legacy_inventory_mutation_routes() -> None:
    sources = {
        "core/services/purchase_service.py": PURCHASE_SERVICE.read_text(encoding="utf-8"),
        "application/purchases/receive_po_adapter.py": RECEIVE_PO_ADAPTER.read_text(encoding="utf-8"),
    }
    forbidden = [
        ".add_stock(",
        ".deduct_stock(",
        "PURCHASE_ITEMS_PROCESS",
        "UPDATE productos SET existencia",
        "inventario_actual",
        "branch_inventory",
        "movimientos_inventario",
    ]
    violations = {
        path: [token for token in forbidden if token in source]
        for path, source in sources.items()
    }
    assert {path: tokens for path, tokens in violations.items() if tokens} == {}
