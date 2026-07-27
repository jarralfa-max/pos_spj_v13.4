import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRODUCTS_UI = ROOT / "modulos/productos.py"
FORBIDDEN = [
    re.compile(r"UPDATE\s+productos\s+SET\s+oculto", re.IGNORECASE),
    re.compile(r"UPDATE\s+productos\s+SET\s+activo", re.IGNORECASE),
]


def test_products_no_direct_catalog_state_sql_in_ui() -> None:
    content = PRODUCTS_UI.read_text(encoding="utf-8")
    violations = [pattern.pattern for pattern in FORBIDDEN if pattern.search(content)]
    assert violations == []
