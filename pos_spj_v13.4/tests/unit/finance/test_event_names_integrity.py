"""Guard: EventName must import cleanly and define no duplicate members.

A duplicate enum member NAME makes ``event_names.py`` fail to import, which
crashes the app at boot (``TypeError: 'X' already defined``). This kind of
corruption is easy to introduce with a bad merge; this test makes it fail
loudly in CI instead of at runtime on a user's machine.
"""

from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / "backend" / "shared" / "events" / "event_names.py"
)

#: A representative slice of the finance/commercial events the bounded context
#: relies on. If any go missing the wiring/handlers break.
REQUIRED_MEMBERS = {
    "CASH_SHIFT_CLOSED",
    "PAYROLL_PAID",
    "SUPPLIER_INVOICE_REGISTERED",
    "INVENTORY_ADJUSTMENT_REGISTERED",
    "JOURNAL_ENTRY_POSTED",
    "JOURNAL_ENTRY_REVERSED",
    "COMMERCIAL_OBLIGATION_RECOGNIZED",
    "COMMERCIAL_OBLIGATION_REDEEMED",
    "COMMERCIAL_OBLIGATION_RELEASED",
    "COMMERCIAL_OBLIGATION_REVERSED",
    "FINANCIAL_STATEMENTS_GENERATED",
    "GIFT_CARD_SOLD",
    "LOYALTY_POINTS_ISSUED",
}


def test_event_names_module_imports_cleanly():
    """A duplicate member name would raise TypeError on import."""
    from backend.shared.events.event_names import EventName

    assert len(list(EventName)) >= 100


def test_no_duplicate_enum_member_names():
    """Static check: no assignment target inside EventName appears twice."""
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    enum_class = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name == "EventName"
    )
    names = [
        target.id
        for stmt in enum_class.body
        if isinstance(stmt, ast.Assign)
        for target in stmt.targets
        if isinstance(target, ast.Name)
    ]
    duplicates = [name for name, count in Counter(names).items() if count > 1]
    assert not duplicates, f"EventName tiene miembros duplicados: {duplicates}"


def test_required_finance_members_present():
    from backend.shared.events.event_names import EventName

    defined = {member.name for member in EventName}
    missing = REQUIRED_MEMBERS - defined
    assert not missing, f"EventName perdió miembros requeridos: {sorted(missing)}"
