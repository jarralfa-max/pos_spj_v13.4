from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRODUCTS_UI = ROOT / "modulos/productos.py"


def test_products_catalog_delete_restore_no_ui_commit() -> None:
    content = PRODUCTS_UI.read_text(encoding="utf-8")
    for marker in ("def eliminar_producto", "def _toggle_activo", "def _restaurar_producto"):
        start = content.index(marker)
        next_def = content.find("\n    def ", start + 1)
        block = content[start:] if next_def == -1 else content[start:next_def]
        assert ".commit(" not in block
        assert ".rollback(" not in block
