from __future__ import annotations

from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
EVENT_WIRING = PACKAGE_ROOT / "backend" / "bootstrap" / "wiring" / "event_wiring.py"
RECEIPT_HANDLER = (PACKAGE_ROOT / "backend" / "application" / "event_handlers" / "inventory"
                   / "purchase_receipt_handler.py")


def test_purchase_and_reception_use_canonical_inventory_service() -> None:
    """La entrada de compras llega al libro canónico de Inventario por el
    cableado vivo (core/app_container.py ya no existe; prueba heredada
    actualizada contra la composición activa)."""
    wiring = EVENT_WIRING.read_text(encoding="utf-8")
    assert "CanonicalPurchaseStockEntryHandler" in wiring
    assert "GoodsReceiptReversedHandler" in wiring        # el reverso también compensa
    assert "PostInventoryMovementUseCase" in RECEIPT_HANDLER.read_text(encoding="utf-8")
    assert not (PACKAGE_ROOT / "core" / "app_container.py").exists()
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
