"""INV-3 (REGLA CERO, §8, §64) — inventory identity is UUIDv7 only.

No INTEGER PRIMARY KEY / AUTOINCREMENT, no lastrowid or MAX(id)+1 as identity,
and no int(..._id) casts of domain identifiers in the inventory context.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
INVENTORY_CODE = [
    REPO / "backend" / "domain" / "inventory",
    REPO / "backend" / "application" / "inventory",
    REPO / "backend" / "infrastructure" / "db" / "repositories" / "inventory",
]
SCHEMA = REPO / "backend" / "infrastructure" / "db" / "schema" / "inventory_schema.py"

_AUTOINCREMENT = re.compile(r"AUTOINCREMENT|INTEGER\s+PRIMARY\s+KEY", re.IGNORECASE)
_LASTROWID = re.compile(r"\blastrowid\b|MAX\s*\(\s*id\s*\)")
_INT_ID_CAST = re.compile(r"\bint\s*\(\s*[\w\.]*_id\b")


def _py_files():
    for root in INVENTORY_CODE:
        if root.is_dir():
            for p in root.rglob("*.py"):
                if "__pycache__" not in p.parts:
                    yield p


def test_schema_has_no_integer_identity():
    text = SCHEMA.read_text(encoding="utf-8")
    assert not _AUTOINCREMENT.search(text), \
        "inventory_schema usa identidad entera; debe ser TEXT UUIDv7"


def test_inventory_code_has_no_integer_identity_patterns():
    offenders = []
    for path in list(_py_files()) + [SCHEMA]:
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _LASTROWID.search(line) or _INT_ID_CAST.search(line):
                offenders.append(f"{path.relative_to(REPO)}:{n}: {line.strip()}")
    assert not offenders, (
        "identidad entera / cast int(_id) en inventario (usar UUIDv7):\n"
        + "\n".join(offenders))
