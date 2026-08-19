"""POS-19 — shared scanners for the Sales/POS desktop module guardrails.

Mirrors `tests/architecture/customers_crm_guardrails.py`'s own shape exactly
— same ratchet philosophy (scans whatever exists today, fails the moment
new code violates the rule).
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

REPO = Path(__file__).resolve().parents[2]

SALES_POS_UI_ROOT = REPO / "frontend" / "desktop" / "modules" / "sales_pos"


def _py_files(root: Path) -> Iterable[Path]:
    if not root.is_dir():
        return
    for path in root.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        yield path


def sales_pos_ui_py_files() -> list[Path]:
    return list(_py_files(SALES_POS_UI_ROOT))


def relative(path: Path) -> str:
    return path.relative_to(REPO).as_posix()
