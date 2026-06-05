from __future__ import annotations

import ast
from pathlib import Path

from modulos.design_tokens import Colors

PACKAGE_ROOT = Path(__file__).resolve().parents[2]


def test_status_background_aliases_exist_and_match_design_system() -> None:
    assert Colors.DANGER_BG == Colors.DANGER.BG_SOFT
    assert Colors.SUCCESS_BG == Colors.SUCCESS.BG_SOFT
    assert Colors.WARNING_BG == Colors.WARNING.BG_SOFT
    assert Colors.INFO_BG == Colors.INFO.BG_SOFT


def test_color_tokens_referenced_by_modules_exist() -> None:
    missing: list[str] = []
    for path in (PACKAGE_ROOT / "modulos").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "Colors"
                and not hasattr(Colors, node.attr)
            ):
                missing.append(f"{path.relative_to(PACKAGE_ROOT)} uses Colors.{node.attr}")
    assert not missing, "Missing design token aliases: " + "; ".join(sorted(set(missing)))
