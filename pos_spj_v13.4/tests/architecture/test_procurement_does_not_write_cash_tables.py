"""PUR-13.11 — procurement never writes cash/treasury tables directly.

Immediate payment is scheduled via SUPPLIER_PAYMENT_SCHEDULED from an authorized
financial source (never POS operative cash), consumed by the Treasury context.
The canonical procurement code must not touch caja/tesorería nor call
registrar_egreso.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PROCUREMENT_ROOTS = [
    REPO / "backend" / "domain" / "procurement",
    REPO / "backend" / "application" / "procurement",
    REPO / "backend" / "infrastructure" / "db" / "repositories" / "procurement",
    REPO / "frontend" / "desktop" / "modules" / "purchasing",
]

_CASH = re.compile(
    r"UPDATE\s+caja\b"
    r"|INSERT\s+INTO\s+caja\b"
    r"|UPDATE\s+tesoreria"
    r"|INSERT\s+INTO\s+tesoreria"
    r"|registrar_egreso\s*\(",
    re.IGNORECASE,
)


def _files():
    for root in PROCUREMENT_ROOTS:
        if root.is_dir():
            for p in root.rglob("*.py"):
                if "__pycache__" not in p.parts:
                    yield p


def test_procurement_does_not_write_cash_tables():
    offenders = []
    for path in _files():
        for m in _CASH.finditer(path.read_text(encoding="utf-8")):
            offenders.append(f"{path.relative_to(REPO)}: {m.group(0)!r}")
    assert not offenders, (
        "Compras no escribe caja/tesorería directamente; emite "
        "SUPPLIER_PAYMENT_SCHEDULED hacia Tesorería:\n" + "\n".join(offenders))
