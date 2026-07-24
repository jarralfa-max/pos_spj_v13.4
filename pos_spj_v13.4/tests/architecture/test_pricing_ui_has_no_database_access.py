"""PRC-7 — the canonical pricing/costing UI never touches the database.

The pricing UI (frontend/desktop/modules/pricing) must delegate every read to the
``PricingReadService`` through the presenter — never SQL, cursors, connections,
repositories or the pricing schema. Presentation-only, es-MX.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
UI_ROOT = REPO / "frontend" / "desktop" / "modules" / "pricing"

_FORBIDDEN = re.compile(
    r"\bimport sqlite3\b"
    r"|\bcursor\b"
    r"|(?:cursor|conn|connection|_conn|db|_db)\s*\.\s*execute\s*\("
    r"|(?:conn|connection|_conn|db|_db)\s*\.\s*(?:commit|rollback)\s*\("
    r"|\b(SELECT|INSERT\s+INTO|UPDATE\s+\w|DELETE\s+FROM)\b"
    r"|infrastructure\.db\.repositories"
    r"|PricingRepository",
    re.IGNORECASE,
)


def _ui_files():
    for p in UI_ROOT.rglob("*.py"):
        if "__pycache__" not in p.parts:
            yield p


def test_pricing_ui_has_no_database_access():
    offenders = []
    for path in _ui_files():
        text = path.read_text(encoding="utf-8")
        for m in _FORBIDDEN.finditer(text):
            offenders.append(f"{path.relative_to(REPO)}: {m.group(0)!r}")
    assert not offenders, (
        "La UI canónica de Precios no debe tocar la base de datos "
        "(usa PricingReadService vía presenter):\n" + "\n".join(offenders))
