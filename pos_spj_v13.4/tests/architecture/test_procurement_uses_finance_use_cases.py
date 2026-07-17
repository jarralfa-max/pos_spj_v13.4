"""PUR-13.11 — procurement reaches Finance/Treasury only through canonical events.

The procurement context must NOT import the finance/treasury services, entities
or repositories directly. Its financial effects travel as canonical events
(PAYABLE_CREATED / SUPPLIER_PAYMENT_SCHEDULED) that the Finance/Treasury contexts
consume. This keeps the bounded contexts decoupled and the money flow auditable.
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

# Direct coupling into other bounded contexts' internals is forbidden.
_FORBIDDEN_IMPORT = re.compile(
    r"from\s+backend\.domain\.finance\b"
    r"|from\s+backend\.application\.finance\b"
    r"|from\s+backend\.infrastructure\.db\.repositories\.finance\b"
    r"|from\s+core\.services\.finance\b"
    r"|from\s+core\.services\.enterprise\.finance_service\b"
    r"|import\s+treasury_service\b"
    r"|FinanceUnitOfWork",
)
# The canonical financial events procurement is allowed to emit.
_CANONICAL_EVENTS = ("PURCHASE_PAYABLE_CREATED", "PURCHASE_PAYMENT_REQUESTED",
                     "PAYABLE_CREATED", "SUPPLIER_PAYMENT_SCHEDULED")


def _files():
    for root in PROCUREMENT_ROOTS:
        if root.is_dir():
            for p in root.rglob("*.py"):
                if "__pycache__" not in p.parts:
                    yield p


def test_procurement_does_not_import_finance_internals():
    offenders = []
    for path in _files():
        for m in _FORBIDDEN_IMPORT.finditer(path.read_text(encoding="utf-8")):
            offenders.append(f"{path.relative_to(REPO)}: {m.group(0)!r}")
    assert not offenders, (
        "Compras no importa internals de Finance/Treasury; usa eventos canónicos:\n"
        + "\n".join(offenders))


def test_procurement_financial_effects_are_events():
    """The integration layer must reference the canonical financial event names."""
    translators = (REPO / "backend/application/procurement/integrations/"
                   "downstream_translators.py").read_text(encoding="utf-8")
    assert "PAYABLE_CREATED" in translators
    assert "SUPPLIER_PAYMENT_SCHEDULED" in translators
