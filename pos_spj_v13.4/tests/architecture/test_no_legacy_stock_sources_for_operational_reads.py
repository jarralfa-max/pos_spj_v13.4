from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WATCHED_FILES = [
    ROOT / "core/services/sales/product_catalog_query_service.py",
    ROOT / "core/services/stock_reservation_service.py",
    ROOT / "core/services/recipes/recipe_resolver.py",
    ROOT / "modulos/ventas.py",
]
FORBIDDEN_PATTERNS = {
    "branch_inventory": re.compile(r"\bbranch_inventory\b", re.IGNORECASE),
    "product_existence_column": re.compile(r"\b(?:p|productos)\.existencia\b|\bSELECT\b[^\n;]*\bexistencia\b", re.IGNORECASE),
    "legacy_inventory_table": re.compile(r"\b(?:FROM|JOIN|UPDATE|INTO)\s+inventory\b", re.IGNORECASE),
}


def test_no_legacy_stock_sources_for_operational_reads() -> None:
    violations: list[str] = []
    for path in WATCHED_FILES:
        content = path.read_text(encoding="utf-8")
        for name, pattern in FORBIDDEN_PATTERNS.items():
            for match in pattern.finditer(content):
                line_no = content.count("\n", 0, match.start()) + 1
                line = content.splitlines()[line_no - 1].strip()
                violations.append(f"{path.relative_to(ROOT)}:{line_no}: {name}: {line}")

    assert violations == []
