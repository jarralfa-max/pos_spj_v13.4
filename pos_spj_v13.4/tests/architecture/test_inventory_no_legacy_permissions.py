from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INVENTORY_UI = ROOT / "modulos/inventario_enterprise.py"


def test_inventory_uses_canonical_permissions() -> None:
    # INV-27 corte: la UI enterprise es de solo lectura (presenter); no lleva
    # cadenas de permiso legacy. Los permisos granulares viven en la navegación
    # canónica (InventoryPermissions), verificada por los tests de INV-25.
    content = INVENTORY_UI.read_text(encoding="utf-8")
    assert '"inventario.entrada"' not in content
    assert '"inventario.ajustar"' not in content
    assert 'INVENTARIO.entrada' not in content
    assert 'INVENTARIO.ajustar' not in content
