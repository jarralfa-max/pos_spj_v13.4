"""PROD-18 — shared scanner for the Products UI module's own guardrails.

`UI_ROOTS` in `architecture_guardrails.py` (the repo-wide "no SQL in UI"
scanner) never included `frontend/desktop/modules/` at all — a gap that
predates and outlives Products specifically (every enterprise UI module built
since, Sales/CRM/Purchasing/Products included, is unscanned by it). Widening
that shared constant is out of scope for a Products-only pass — it would
change guardrail coverage for every other module in the same commit. This
file instead mirrors `customers_crm_guardrails.py`'s own established pattern:
a small, module-scoped scanner, so a real gap ("false confidence" — clean by
manual inspection, not by CI) closes without a repo-wide blast radius.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

REPO = Path(__file__).resolve().parents[2]

PRODUCTS_UI_ROOT = REPO / "frontend" / "desktop" / "modules" / "products"


def _py_files(root: Path) -> Iterable[Path]:
    if not root.is_dir():
        return
    for path in root.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        yield path


def products_ui_py_files() -> list[Path]:
    return list(_py_files(PRODUCTS_UI_ROOT))


def relative(path: Path) -> str:
    return path.relative_to(REPO).as_posix()
