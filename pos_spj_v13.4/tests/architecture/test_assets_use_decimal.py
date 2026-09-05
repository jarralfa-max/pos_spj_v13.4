"""ASSET-1 (§8, §64, §99, §110) — Activos is Decimal-only, never float, for
any monetary/cost amount. AST-based so docstrings/comments that merely
mention "float" (e.g. `isinstance(x, float)` guards) never trigger.
"""

from __future__ import annotations

import ast
import re

from tests.architecture.assets_guardrails import (
    ASSET_SCHEMA_FILE,
    asset_backend_py_files,
    relative,
)

_REAL_COLUMN = re.compile(r"^\s*\w+\s+REAL\b", re.IGNORECASE)


def _is_float_name(node: ast.AST) -> bool:
    return isinstance(node, ast.Name) and node.id == "float"


def test_assets_code_has_no_float_usage():
    offenders = []
    for path in asset_backend_py_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _is_float_name(node.func):
                offenders.append(f"{relative(path)}:{node.lineno}: float() call")
            if isinstance(node, ast.AnnAssign) and node.annotation is not None \
                    and _is_float_name(node.annotation):
                offenders.append(f"{relative(path)}:{node.lineno}: float annotation")
            if isinstance(node, ast.arg) and node.annotation is not None \
                    and _is_float_name(node.annotation):
                offenders.append(f"{relative(path)}:{node.lineno}: float arg")
            if isinstance(node, ast.FunctionDef) and node.returns is not None \
                    and _is_float_name(node.returns):
                offenders.append(f"{relative(path)}:{node.lineno}: -> float")
    assert not offenders, "uso de float en Activos (usar Decimal/Money):\n" + "\n".join(offenders)


def test_assets_schema_has_no_real_columns():
    if not ASSET_SCHEMA_FILE.exists():
        return
    offenders = [
        line.strip() for line in ASSET_SCHEMA_FILE.read_text(encoding="utf-8").splitlines()
        if _REAL_COLUMN.search(line)
    ]
    assert not offenders, "columnas REAL en assets_schema (usar TEXT/Decimal):\n" + "\n".join(offenders)
