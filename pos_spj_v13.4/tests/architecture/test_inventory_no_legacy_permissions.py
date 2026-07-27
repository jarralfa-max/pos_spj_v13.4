from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INVENTORY_UI = ROOT / "modulos/inventario_local.py"


def test_inventory_uses_canonical_permissions() -> None:
    content = INVENTORY_UI.read_text(encoding="utf-8")
    assert '"inventario.entrada"' not in content
    assert '"inventario.ajustar"' not in content
    assert '"INVENTARIO.entrada"' in content
    assert '"INVENTARIO.ajustar"' in content
