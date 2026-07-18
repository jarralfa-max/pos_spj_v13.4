"""INV-3 (§8, §64) — the inventory context is Decimal-only, never float.

No float type annotations, no float() coercions of quantities/weights, and no
REAL columns in the inventory schema. Detection is AST-based for Python code so
docstrings/comments that merely mention "float" (e.g. "float is rejected") do
not trigger; isinstance(x, float) guards are fine — they reject float.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
INVENTORY_CODE = [
    REPO / "backend" / "domain" / "inventory",
    REPO / "backend" / "application" / "inventory",
    REPO / "backend" / "infrastructure" / "db" / "repositories" / "inventory",
]
SCHEMA = REPO / "backend" / "infrastructure" / "db" / "schema" / "inventory_schema.py"

# A column declaration line whose SQL type is REAL: "<name> REAL ...".
_REAL_COLUMN = re.compile(r"^\s*\w+\s+REAL\b", re.IGNORECASE)


def _py_files():
    for root in INVENTORY_CODE:
        if root.is_dir():
            for p in root.rglob("*.py"):
                if "__pycache__" not in p.parts:
                    yield p


def _is_float_name(node: ast.AST) -> bool:
    return isinstance(node, ast.Name) and node.id == "float"


def test_no_float_usage_in_inventory_code():
    offenders = []
    for path in _py_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            # float() coercion call
            if isinstance(node, ast.Call) and _is_float_name(node.func):
                offenders.append(f"{path.relative_to(REPO)}:{node.lineno}: float() call")
            # : float / -> float annotations
            if isinstance(node, ast.AnnAssign) and _is_float_name(node.annotation):
                offenders.append(f"{path.relative_to(REPO)}:{node.lineno}: float annotation")
            if isinstance(node, ast.arg) and node.annotation is not None \
                    and _is_float_name(node.annotation):
                offenders.append(f"{path.relative_to(REPO)}:{node.lineno}: float arg")
            if isinstance(node, ast.FunctionDef) and node.returns is not None \
                    and _is_float_name(node.returns):
                offenders.append(f"{path.relative_to(REPO)}:{node.lineno}: -> float")
    assert not offenders, "float usage in inventory (usar Decimal):\n" + "\n".join(offenders)


def test_no_real_columns_in_inventory_schema():
    offenders = [
        line.strip()
        for line in SCHEMA.read_text(encoding="utf-8").splitlines()
        if _REAL_COLUMN.search(line)
    ]
    assert not offenders, "columnas REAL en inventory_schema (usar TEXT decimal):\n" + \
        "\n".join(offenders)
