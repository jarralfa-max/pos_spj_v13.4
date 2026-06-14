from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRODUCTS_UI = ROOT / "modulos/productos.py"


def test_products_uses_canonical_permissions() -> None:
    content = PRODUCTS_UI.read_text(encoding="utf-8")
    for legacy in ('"productos.crear"', '"productos.editar"', '"productos.eliminar"'):
        assert legacy not in content
    for canonical in ('"PRODUCTOS.crear"', '"PRODUCTOS.editar"', '"PRODUCTOS.eliminar"'):
        assert canonical in content
