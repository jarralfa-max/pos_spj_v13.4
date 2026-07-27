from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SALES_UI = ROOT / "modulos/ventas.py"


def test_sales_catalog_search_uses_query_service_only() -> None:
    content = SALES_UI.read_text(encoding="utf-8")
    start = content.index("def _buscar_productos_catalogo")
    next_def = content.find("\n    def ", start + 1)
    block = content[start:] if next_def == -1 else content[start:next_def]
    assert "list_visible_products" in block
    assert ".execute(" not in block
    assert ".cursor(" not in block
