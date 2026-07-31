from __future__ import annotations

from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
APP_CONTAINER = PACKAGE_ROOT / "core" / "app_container.py"


def test_purchase_and_reception_use_canonical_inventory_service() -> None:
    container_source = APP_CONTAINER.read_text(encoding="utf-8")
    assert "InventoryApplicationService" in container_source
    assert "InventoryRepository" in container_source
    assert not (PACKAGE_ROOT / "application" / "purchases").exists()
    assert not (PACKAGE_ROOT / "core" / "services" / "purchase_service.py").exists()


def test_purchase_and_reception_do_not_use_legacy_inventory_mutation_routes() -> None:
    roots = (PACKAGE_ROOT / "backend" / "application" / "procurement",
             PACKAGE_ROOT / "backend" / "domain" / "procurement")
    sources = {str(path.relative_to(PACKAGE_ROOT)): path.read_text(encoding="utf-8")
               for root in roots for path in root.rglob("*.py")}
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
